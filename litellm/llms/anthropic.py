import os, json
from enum import Enum
import requests
import time
from typing import Callable
from litellm.utils import ModelResponse
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT

anthropic = Anthropic()


class AnthropicError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(self.message)  # Call the base class constructor with the parameters it needs


class AnthropicLLM:
    def __init__(self, encoding, default_max_tokens_to_sample, logging_obj, api_key=None):
        self.encoding = encoding
        self.default_max_tokens_to_sample = default_max_tokens_to_sample
        self.completion_url = "https://api.anthropic.com/v1/complete"
        self.api_key = api_key
        self.logging_obj = logging_obj
        self.validate_environment(api_key=api_key)

    def validate_environment(self, api_key):  # set up the environment required to run the model
        # set the api key
        if self.api_key is None:
            raise ValueError(
                "Missing Anthropic API Key - A call is being made to anthropic"
                + " but no key is set either in the environment variables or via params"
            )
        self.api_key = api_key
        self.headers = {
            "accept": "application/json",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "x-api-key": self.api_key,
        }

    def completion(
        self,
        model: str,
        messages: list,
        model_response: ModelResponse,
        print_verbose: Callable,
        optional_params=None,
        litellm_params=None,
        logger_fn=None,
    ):  # logic for parsing in - calling - parsing out model completion calls
        model = model
        prompt = f"{HUMAN_PROMPT}"
        for message in messages:
            if "role" in message:
                if message["role"] == "user":
                    prompt += f"{HUMAN_PROMPT}{message['content']}"
                else:
                    prompt += f"{AI_PROMPT}{message['content']}"
            else:
                prompt += f"{HUMAN_PROMPT}{message['content']}"
        prompt += f"{AI_PROMPT}"
        if "max_tokens" in optional_params and optional_params["max_tokens"] != float("inf"):
            max_tokens = optional_params["max_tokens"]
        else:
            max_tokens = self.default_max_tokens_to_sample

        # LOGGING
        self.logging_obj.pre_call(
            input=prompt,
            api_key=self.api_key,
            additional_args={
                "complete_input_dict": {"model": model, "prompt": prompt, "max_tokens_to_sample": max_tokens}
            },
        )
        # COMPLETION CALL
        if "stream" in optional_params and optional_params["stream"] is True:
            stream = anthropic.completions.create(
                prompt=prompt,
                max_tokens_to_sample=max_tokens,
                model=model,
                stream=True,
            )
            return stream
        else:
            completion_response = anthropic.completions.create(
                prompt=prompt,
                max_tokens_to_sample=max_tokens,
                model=model,
                stream=False,
            )
            # LOGGING
            self.logging_obj.post_call(
                input=prompt,
                api_key=self.api_key,
                original_response=completion_response.completion,
                additional_args={
                    "complete_input_dict": {"model": model, "prompt": prompt, "max_tokens_to_sample": max_tokens}
                },
            )
            print_verbose(f"raw model_response: {completion_response.completion}")
            # RESPONSE OBJECT
            if "error" in completion_response:
                raise AnthropicError(
                    message=completion_response["error"],
                    status_code=completion_response.status_code,
                )
            else:
                model_response["choices"][0]["message"]["content"] = completion_response.completion

            # CALCULATING USAGE
            prompt_tokens = len(self.encoding.encode(prompt))  # [TODO] use the anthropic tokenizer here
            completion_tokens = len(
                self.encoding.encode(model_response["choices"][0]["message"]["content"])
            )  # [TODO] use the anthropic tokenizer here

            model_response["created"] = time.time()
            model_response["model"] = model
            model_response["usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }
            return model_response

    def embedding(
        self,
    ):  # logic for parsing in - calling - parsing out model embedding calls
        pass
