# +-----------------------------------------------+
# |                                               |
# |               PII Masking                     |
# |         with Microsoft Presidio               |
# |   https://github.com/BerriAI/litellm/issues/  |
# +-----------------------------------------------+
#
#  Tell us how we can improve! - Krrish & Ishaan


import asyncio
import json
import traceback
import uuid
from typing import Any, List, Optional, Tuple, Union

import aiohttp
from fastapi import HTTPException

import litellm  # noqa: E401
from litellm._logging import verbose_proxy_logger
from litellm.caching import DualCache
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.utils import (
    EmbeddingResponse,
    ImageResponse,
    ModelResponse,
    StreamingChoices,
    get_formatted_prompt,
)


class _OPTIONAL_PresidioPIIMasking(CustomLogger):
    user_api_key_cache = None
    ad_hoc_recognizers = None

    # Class variables or attributes
    def __init__(
        self,
        logging_only: Optional[bool] = None,
        mock_testing: bool = False,
        mock_redacted_text: Optional[dict] = None,
    ):
        self.pii_tokens: dict = (
            {}
        )  # mapping of PII token to original text - only used with Presidio `replace` operation

        self.mock_redacted_text = mock_redacted_text
        self.logging_only = logging_only
        if mock_testing is True:  # for testing purposes only
            return

        ad_hoc_recognizers = litellm.presidio_ad_hoc_recognizers
        if ad_hoc_recognizers is not None:
            try:
                with open(ad_hoc_recognizers, "r") as file:
                    self.ad_hoc_recognizers = json.load(file)
            except FileNotFoundError:
                raise Exception(f"File not found. file_path={ad_hoc_recognizers}")
            except json.JSONDecodeError as e:
                raise Exception(
                    f"Error decoding JSON file: {str(e)}, file_path={ad_hoc_recognizers}"
                )
            except Exception as e:
                raise Exception(
                    f"An error occurred: {str(e)}, file_path={ad_hoc_recognizers}"
                )

        self.validate_environment()

    def validate_environment(self):
        self.presidio_analyzer_api_base: Optional[str] = litellm.get_secret(
            "PRESIDIO_ANALYZER_API_BASE", None
        )  # type: ignore
        self.presidio_anonymizer_api_base: Optional[str] = litellm.get_secret(
            "PRESIDIO_ANONYMIZER_API_BASE", None
        )  # type: ignore

        if self.presidio_analyzer_api_base is None:
            raise Exception("Missing `PRESIDIO_ANALYZER_API_BASE` from environment")
        if not self.presidio_analyzer_api_base.endswith("/"):
            self.presidio_analyzer_api_base += "/"
        if not (
            self.presidio_analyzer_api_base.startswith("http://")
            or self.presidio_analyzer_api_base.startswith("https://")
        ):
            # add http:// if unset, assume communicating over private network - e.g. render
            self.presidio_analyzer_api_base = (
                "http://" + self.presidio_analyzer_api_base
            )

        if self.presidio_anonymizer_api_base is None:
            raise Exception("Missing `PRESIDIO_ANONYMIZER_API_BASE` from environment")
        if not self.presidio_anonymizer_api_base.endswith("/"):
            self.presidio_anonymizer_api_base += "/"
        if not (
            self.presidio_anonymizer_api_base.startswith("http://")
            or self.presidio_anonymizer_api_base.startswith("https://")
        ):
            # add http:// if unset, assume communicating over private network - e.g. render
            self.presidio_anonymizer_api_base = (
                "http://" + self.presidio_anonymizer_api_base
            )

    def print_verbose(self, print_statement):
        try:
            verbose_proxy_logger.debug(print_statement)
            if litellm.set_verbose:
                print(print_statement)  # noqa
        except:
            pass

    async def check_pii(self, text: str, output_parse_pii: bool) -> str:
        """
        [TODO] make this more performant for high-throughput scenario
        """
        try:
            async with aiohttp.ClientSession() as session:
                if self.mock_redacted_text is not None:
                    anonymize_results = self.mock_redacted_text
                else:
                    anonymize_results = None

                    # Make the first request to /analyze
                    analyze_results = await self.presidio_analyze_text(text, session)
                    # Make the second request to /anonymize
                    anonymize_results = await self.presidio_anonymize_text(analyze_results, text, session)

                if anonymize_results is not None:
                    verbose_proxy_logger.debug("redacted_text: %s", anonymize_results)

                    if output_parse_pii is False:
                        return anonymize_results["text"]

                    return self.create_reversible_mask(text, analyze_results, anonymize_results)

                else:
                    raise Exception(f"Invalid anonymizer response: {anonymize_results}")
        except Exception as e:
            verbose_proxy_logger.error(
                "litellm.proxy.hooks.presidio_pii_masking.py::async_pre_call_hook(): Exception occured - {}".format(
                    str(e)
                )
            )
            verbose_proxy_logger.debug(traceback.format_exc())
            raise e

    async def presidio_analyze_text(self, text, session):
        analyze_url = f"{self.presidio_analyzer_api_base}analyze"
        verbose_proxy_logger.debug("Making request to: %s", analyze_url)
        analyze_payload = {"text": text, "language": "en"}
        if self.ad_hoc_recognizers is not None:
            analyze_payload["ad_hoc_recognizers"] = self.ad_hoc_recognizers
        async with session.post(analyze_url, json=analyze_payload) as response:
            return await response.json()

    async def presidio_anonymize_text(self, analyze_results, text, session):
        anonymize_url = f"{self.presidio_anonymizer_api_base}anonymize"
        verbose_proxy_logger.debug("Making request to: %s", anonymize_url)
        anonymize_payload = {
            "text": text,
            "analyzer_results": analyze_results,
        }

        async with session.post(anonymize_url, json=anonymize_payload) as response:
            return await response.json()

    def create_reversible_mask(self, text, analyze_results, anonymize_results):
        sorted_analyze_results = self.sort_items_by_start(analyze_results)
        sorted_anonymize_results = {
            "masked_text": anonymize_results["text"],
            "items": self.ensure_mask_text_uniqueness(self.sort_items_by_start(anonymize_results["items"])),
        }

        all_items = self.merge_items(sorted_analyze_results, sorted_anonymize_results)

        return self.set_pii_tokens_and_update_mask_text(text, all_items)

    def sort_items_by_start(self, items):
        return sorted(items, key=lambda x: x["start"])

    def ensure_mask_text_uniqueness(self, items):
        mask_texts = {}
        results = []
        for item in items:
            entity_type = item["entity_type"]
            if entity_type not in mask_texts:
                mask_texts[entity_type] = 0
            else:
                mask_texts[entity_type] += 1

            results.append({**item, "text": f"<{entity_type}-{mask_texts[entity_type]}>"})

        return results

    def merge_items(self, analyze_results, anonymize_results):
        return {
            "masked_text": anonymize_results["masked_text"],
            "items": [
                {
                    "mask_start": item["start"],
                    "mask_end": item["end"],
                    "mask_text": item["text"],
                    "operator": item["operator"],
                    "original_start": analyze_results[idx]["start"],
                    "original_end": analyze_results[idx]["end"],
                    "entity_type": analyze_results[idx]["entity_type"],
                }
                for idx, item in enumerate(anonymize_results["items"])
            ],
        }

    def set_pii_tokens_and_update_mask_text(self, full_original_text, all_items):
        final_text = full_original_text
        current_diff = 0
        for item in all_items["items"]:
            if item["operator"] == "replace":
                start = item["original_start"] + current_diff
                end = item["original_end"] + current_diff
                mask_text = item["mask_text"]

                final_text = final_text[:start] + mask_text + final_text[end:]

                current_diff = current_diff + len(mask_text) - (end - start)

                original_unmasked_text = full_original_text[item["original_start"] : item["original_end"]]
                self.pii_tokens[item["mask_text"]] = original_unmasked_text

        return final_text

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: str,
    ):
        """
        - Check if request turned off pii
            - Check if user allowed to turn off pii (key permissions -> 'allow_pii_controls')

        - Take the request data
        - Call /analyze -> get the results
        - Call /anonymize w/ the analyze results -> get the redacted text

        For multiple messages in /chat/completions, we'll need to call them in parallel.
        """
        try:
            if (
                self.logging_only is True
            ):  # only modify the logging obj data (done by async_logging_hook)
                return data
            permissions = user_api_key_dict.permissions
            output_parse_pii = permissions.get(
                "output_parse_pii", litellm.output_parse_pii
            )  # allow key to turn on/off output parsing for pii
            no_pii = permissions.get(
                "no-pii", None
            )  # allow key to turn on/off pii masking (if user is allowed to set pii controls, then they can override the key defaults)

            if no_pii is None:
                # check older way of turning on/off pii
                no_pii = not permissions.get("pii", True)

            content_safety = data.get("content_safety", None)
            verbose_proxy_logger.debug("content_safety: %s", content_safety)
            ## Request-level turn on/off PII controls ##
            if content_safety is not None and isinstance(content_safety, dict):
                # pii masking ##
                if (
                    content_safety.get("no-pii", None) is not None
                    and content_safety.get("no-pii") == True
                ):
                    # check if user allowed to turn this off
                    if permissions.get("allow_pii_controls", False) == False:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "error": "Not allowed to set PII controls per request"
                            },
                        )
                    else:  # user allowed to turn off pii masking
                        no_pii = content_safety.get("no-pii")
                        if not isinstance(no_pii, bool):
                            raise HTTPException(
                                status_code=400,
                                detail={"error": "no_pii needs to be a boolean value"},
                            )
                ## pii output parsing ##
                if content_safety.get("output_parse_pii", None) is not None:
                    # check if user allowed to turn this off
                    if permissions.get("allow_pii_controls", False) == False:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "error": "Not allowed to set PII controls per request"
                            },
                        )
                    else:  # user allowed to turn on/off pii output parsing
                        output_parse_pii = content_safety.get("output_parse_pii")
                        if not isinstance(output_parse_pii, bool):
                            raise HTTPException(
                                status_code=400,
                                detail={
                                    "error": "output_parse_pii needs to be a boolean value"
                                },
                            )

            if no_pii is True:  # turn off pii masking
                return data

            if call_type == "completion":  # /chat/completions requests
                messages = data["messages"]
                tasks = []

                for m in messages:
                    if isinstance(m["content"], str):
                        tasks.append(
                            self.check_pii(
                                text=m["content"], output_parse_pii=output_parse_pii
                            )
                        )
                responses = await asyncio.gather(*tasks)
                for index, r in enumerate(responses):
                    if isinstance(messages[index]["content"], str):
                        messages[index][
                            "content"
                        ] = r  # replace content with redacted string
                verbose_proxy_logger.info(
                    f"Presidio PII Masking: Redacted pii message: {data['messages']}"
                )
            return data
        except Exception as e:
            verbose_proxy_logger.info(
                f"An error occurred -",
            )
            raise e

    async def async_logging_hook(
        self, kwargs: dict, result: Any, call_type: str
    ) -> Tuple[dict, Any]:
        """
        Masks the input before logging to langfuse, datadog, etc.
        """
        if (
            call_type == "completion" or call_type == "acompletion"
        ):  # /chat/completions requests
            messages: Optional[List] = kwargs.get("messages", None)
            tasks = []

            if messages is None:
                return kwargs, result

            for m in messages:
                text_str = ""
                if m["content"] is None:
                    continue
                if isinstance(m["content"], str):
                    text_str = m["content"]
                    tasks.append(
                        self.check_pii(text=text_str, output_parse_pii=False)
                    )  # need to pass separately b/c presidio has context window limits
            responses = await asyncio.gather(*tasks)
            for index, r in enumerate(responses):
                if isinstance(messages[index]["content"], str):
                    messages[index][
                        "content"
                    ] = r  # replace content with redacted string
            verbose_proxy_logger.info(
                f"Presidio PII Masking: Redacted pii message: {messages}"
            )
            kwargs["messages"] = messages

        return kwargs, responses

    async def async_post_call_success_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        response: Union[ModelResponse, EmbeddingResponse, ImageResponse],
    ):
        """
        Output parse the response object to replace the masked tokens with user sent values
        """
        verbose_proxy_logger.debug(
            f"PII Masking Args: litellm.output_parse_pii={litellm.output_parse_pii}; type of response={type(response)}"
        )
        if litellm.output_parse_pii == False:
            return response

        if isinstance(response, ModelResponse) and not isinstance(
            response.choices[0], StreamingChoices
        ):  # /chat/completions requests
            if isinstance(response.choices[0].message.content, str):
                verbose_proxy_logger.debug(
                    f"self.pii_tokens: {self.pii_tokens}; initial response: {response.choices[0].message.content}"
                )
                for key, value in self.pii_tokens.items():
                    response.choices[0].message.content = response.choices[
                        0
                    ].message.content.replace(key, value)
        return response
