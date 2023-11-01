from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Union

import litellm


class Router:
    """
    Example usage:
    from litellm import Router
    model_list = [{
        "model_name": "gpt-3.5-turbo", # openai model name
        "litellm_params": { # params for litellm completion/embedding call
            "model": "azure/<your-deployment-name>",
            "api_key": <your-api-key>,
            "api_version": <your-api-version>,
            "api_base": <your-api-base>
        },
        "tpm": <your-model-tpm>, e.g. 240000
        "rpm": <your-model-rpm>, e.g. 1800
    }]

    router = Router(model_list=model_list)
    """
    model_map: dict = {}
    model_names: List[str] = []
    cache_responses: bool = False
    default_cache_time_seconds: int = 1 * 60 * 60  # 1 hour

    def __init__(self,
                 model_list: Optional[list] = None,
                 redis_host: Optional[str] = None,
                 redis_port: Optional[int] = None,
                 redis_password: Optional[str] = None,
                 cache_responses: bool = False) -> None:
        if model_list:
            self.set_model_list(model_list)
        if redis_host is not None and redis_port is not None and redis_password is not None:
            cache_config = {
                'type': 'redis',
                'host': redis_host,
                'port': redis_port,
                'password': redis_password
            }
        else:  # use an in-memory cache
            cache_config = {
                "type": "local"
            }
        self.cache = litellm.Cache(**cache_config)  # use Redis for tracking load balancing
        if cache_responses:
            litellm.cache = litellm.Cache(**cache_config)  # use Redis for caching completion requests
            self.cache_responses = cache_responses
        litellm.success_callback = [self.deployment_callback]

    def completion(self,
                   model: str,
                   messages: List[Dict[str, str]],
                   is_retry: Optional[bool] = False,
                   is_fallback: Optional[bool] = False,
                   **kwargs) -> litellm.ModelResponse:
        """
        Example usage:
        response = router.completion(model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hey, how's it going?"}]
        """

        # pick the one that is available (lowest TPM/RPM)
        deployment = self.get_available_deployment(model=model, messages=messages)
        data = deployment["litellm_params"]
        # call via litellm.completion()
        return litellm.completion(**{**data, "messages": messages, "caching": self.cache_responses, **kwargs})

    async def acompletion(self,
                          model: str,
                          messages: List[Dict[str, str]],
                          is_retry: Optional[bool] = False,
                          is_fallback: Optional[bool] = False,
                          **kwargs) -> litellm.ModelResponse:
        # pick the one that is available (lowest TPM/RPM)
        deployment = self.get_available_deployment(model=model, messages=messages)
        data = deployment["litellm_params"]
        return await litellm.acompletion(**{**data, "messages": messages, "caching": self.cache_responses, **kwargs})

    def text_completion(self,
                        model: str,
                        prompt: str,
                        is_retry: Optional[bool] = False,
                        is_fallback: Optional[bool] = False,
                        is_async: Optional[bool] = False,
                        **kwargs) -> dict:

        messages = [{"role": "user", "content": prompt}]
        # pick the one that is available (lowest TPM/RPM)
        deployment = self.get_available_deployment(model=model, messages=messages)

        data = deployment["litellm_params"]
        # call via litellm.completion()
        return litellm.text_completion(**{**data, "prompt": prompt, "caching": self.cache_responses, **kwargs})

    def embedding(self,
                  model: str,
                  input: Union[str, List],
                  is_async: Optional[bool] = False,
                  **kwargs) -> Union[List[float], None]:
        # pick the one that is available (lowest TPM/RPM)
        deployment = self.get_available_deployment(model=model, input=input)

        data = deployment["litellm_params"]
        # call via litellm.embedding()
        return litellm.embedding(**{**data, "input": input, "caching": self.cache_responses, **kwargs})

    async def aembedding(self,
                         model: str,
                         input: Union[str, List],
                         is_async: Optional[bool] = True,
                         **kwargs) -> Union[List[float], None]:
        # pick the one that is available (lowest TPM/RPM)
        deployment = self.get_available_deployment(model=model, input=input)

        data = deployment["litellm_params"]
        return await litellm.aembedding(**{**data, "input": input, "caching": self.cache_responses, **kwargs})

    @staticmethod
    def _is_valid_model(model: dict) -> bool:
        """
        Validates that the model has the correct keys
        """
        required_keys = ["model_name", "litellm_params", "tpm", "rpm"]
        return all(key in model for key in required_keys)

    def set_model_list(self, model_list: list) -> None:
        model_map = defaultdict(list)
        for idx, model in enumerate(model_list):
            if not self._is_valid_model(model):
                raise ValueError(f"Invalid model at index {idx}")

            model_map[model["model_name"]].append(model)
        self.model_map = dict(model_map)
        self.model_names = list(model_map.keys())

    def get_model_names(self) -> List[str]:
        return self.model_names

    def deployment_callback(
            self,
            kwargs,  # kwargs to completion
            completion_response,  # response from completion
            start_time, end_time  # start/end time
    ) -> None:
        """
        Function LiteLLM submits a callback to after a successful
        completion. Purpose of this is ti update TPM/RPM usage per model
        """
        model_name = kwargs.get('model', None)  # i.e. gpt35turbo
        custom_llm_provider = kwargs.get("litellm_params", {}).get('custom_llm_provider', None)  # i.e. azure
        if custom_llm_provider:
            model_name = f"{custom_llm_provider}/{model_name}"
        total_tokens = completion_response['usage']['total_tokens']
        self._set_deployment_usage(model_name, total_tokens)

    def get_available_deployment(self,
                                 model: str,
                                 messages: Optional[List[Dict[str, str]]] = None,
                                 input: Optional[Union[str, List]] = None) -> dict:
        """
        Returns a deployment with the lowest TPM/RPM usage.
        """
        # get list of potential deployments
        potential_deployments = self.model_map[model]

        # set first model as current model to calculate token count
        deployment = potential_deployments[0]

        # get model tpm, rpm limits
        tpm, rpm = deployment["tpm"], deployment["rpm"]

        # get deployment current usage
        current_tpm, current_rpm = self._get_deployment_usage(deployment_name=deployment["litellm_params"]["model"])

        # get encoding
        token_count = 0
        if messages is not None:
            token_count = litellm.token_counter(model=deployment["model_name"], messages=messages)
        elif input is not None:
            if isinstance(input, List):
                input_text = "".join(text for text in input)
            else:
                input_text = input
            token_count = litellm.token_counter(model=deployment["model_name"], text=input_text)
        else:
            raise ValueError("Either messages or input must be provided.")

        # -----------------------
        # Find lowest used model
        # ----------------------
        lowest_tpm = float("inf")
        deployment = None

        # Go through all the models to get tpm, rpm
        for item in potential_deployments:
            item_tpm, item_rpm = self._get_deployment_usage(deployment_name=item["litellm_params"]["model"])

            if item_tpm == 0:
                return item
            elif item_tpm + token_count > item["tpm"] or item_rpm + 1 >= item["rpm"]:
                continue
            elif item_tpm < lowest_tpm:
                lowest_tpm = item_tpm
                deployment = item

        # if none, raise exception
        if deployment is None:
            raise ValueError("No models available.")

        # return model
        return deployment

    def _get_deployment_usage(
            self,
            deployment_name: str
    ) -> tuple[int, int]:
        # ------------
        # Setup values
        # ------------
        current_minute = datetime.now().strftime("%H-%M")
        tpm_key = f'{deployment_name}:tpm:{current_minute}'
        rpm_key = f'{deployment_name}:rpm:{current_minute}'

        # ------------
        # Return usage
        # ------------
        tpm = self.cache.get_cache(cache_key=tpm_key) or 0
        rpm = self.cache.get_cache(cache_key=rpm_key) or 0

        return int(tpm), int(rpm)

    def increment(self, key: str, increment_value: int) -> None:
        # get value
        cached_value = self.cache.get_cache(cache_key=key)
        # update value
        try:
            cached_value += increment_value
        except TypeError:
            cached_value = increment_value
        # save updated value
        self.cache.add_cache(result=cached_value, cache_key=key, ttl=self.default_cache_time_seconds)

    def _set_deployment_usage(
            self,
            model_name: str,
            total_tokens: int
    ) -> None:
        # ------------
        # Setup values
        # ------------
        current_minute = datetime.now().strftime("%H-%M")
        tpm_key = f'{model_name}:tpm:{current_minute}'
        rpm_key = f'{model_name}:rpm:{current_minute}'

        # ------------
        # Update usage
        # ------------
        self.increment(tpm_key, total_tokens)
        self.increment(rpm_key, 1)
