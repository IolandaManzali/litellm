import json
from typing import Callable, Optional, Union

import httpx

import litellm
from litellm.llms.custom_httpx.http_handler import (
    AsyncHTTPHandler,
    HTTPHandler,
    get_async_httpx_client,
)
from litellm.types.utils import ModelResponse
from litellm.utils import CustomStreamWrapper, get_secret

from ...base_aws_llm import BaseAWSLLM
from ..common_utils import BedrockError

# class FakeBedrockConverseLLM(BaseAWSLLM):
#     def __init__(self) -> None:
#         super().__init__()

#     async def async_completion(
#         self,
#         model: str,
#         messages: list,
#         api_base: str,
#         model_response: ModelResponse,
#         print_verbose: Callable,
#         data: str,
#         timeout: Optional[Union[float, httpx.Timeout]],
#         encoding,
#         logging_obj,
#         stream,
#         optional_params: dict,
#         litellm_params=None,
#         logger_fn=None,
#         headers={},
#         client: Optional[AsyncHTTPHandler] = None,
#     ) -> Union[ModelResponse, CustomStreamWrapper]:
#         if client is None or not isinstance(client, AsyncHTTPHandler):
#             _params = {}
#             if timeout is not None:
#                 if isinstance(timeout, float) or isinstance(timeout, int):
#                     timeout = httpx.Timeout(timeout)
#                 _params["timeout"] = timeout
#             client = get_async_httpx_client(
#                 params=_params, llm_provider=litellm.LlmProviders.BEDROCK
#             )
#         else:
#             client = client  # type: ignore

#         try:
#             response = await client.post(url=api_base, headers=headers, data=data)  # type: ignore
#             response.raise_for_status()
#         except httpx.HTTPStatusError as err:
#             error_code = err.response.status_code
#             raise BedrockError(status_code=error_code, message=err.response.text)
#         except httpx.TimeoutException as e:
#             raise BedrockError(status_code=408, message="Timeout error occurred.")

#         return litellm.AmazonConverseConfig()._transform_response(
#             model=model,
#             response=response,
#             model_response=model_response,
#             stream=stream if isinstance(stream, bool) else False,
#             logging_obj=logging_obj,
#             api_key="",
#             data=data,
#             messages=messages,
#             print_verbose=print_verbose,
#             optional_params=optional_params,
#             encoding=encoding,
#         )

#     def completion(
#         self,
#         model: str,
#         messages: list,
#         api_base: Optional[str],
#         custom_prompt_dict: dict,
#         model_response: ModelResponse,
#         print_verbose: Callable,
#         encoding,
#         logging_obj,
#         optional_params: dict,
#         acompletion: bool,
#         timeout: Optional[Union[float, httpx.Timeout]],
#         litellm_params: dict,
#         logger_fn=None,
#         extra_headers: Optional[dict] = None,
#         client: Optional[Union[AsyncHTTPHandler, HTTPHandler]] = None,
#     ):
#         try:
#             import boto3
#             from botocore.auth import SigV4Auth
#             from botocore.awsrequest import AWSRequest
#             from botocore.credentials import Credentials
#         except ImportError:
#             raise ImportError("Missing boto3 to call bedrock. Run 'pip install boto3'.")

#         ## SETUP ##
#         stream = optional_params.pop("stream", None)
#         modelId = optional_params.pop("model_id", None)
#         if modelId is not None:
#             modelId = self.encode_model_id(model_id=modelId)
#         else:
#             modelId = model

#         provider = model.split(".")[0]

#         # CREDENTIALS
#         # pop aws_secret_access_key, aws_access_key_id, aws_region_name from kwargs, since completion calls fail with them
#         aws_secret_access_key = optional_params.pop("aws_secret_access_key", None)
#         aws_access_key_id = optional_params.pop("aws_access_key_id", None)
#         aws_session_token = optional_params.pop("aws_session_token", None)
#         aws_region_name = optional_params.pop("aws_region_name", None)
#         aws_role_name = optional_params.pop("aws_role_name", None)
#         aws_session_name = optional_params.pop("aws_session_name", None)
#         aws_profile_name = optional_params.pop("aws_profile_name", None)
#         aws_bedrock_runtime_endpoint = optional_params.pop(
#             "aws_bedrock_runtime_endpoint", None
#         )  # https://bedrock-runtime.{region_name}.amazonaws.com
#         aws_web_identity_token = optional_params.pop("aws_web_identity_token", None)
#         aws_sts_endpoint = optional_params.pop("aws_sts_endpoint", None)

#         # if aws_region_name is None:
#         #     # check env #
#         #     litellm_aws_region_name = get_secret("AWS_REGION_NAME", None)

#         #     if litellm_aws_region_name is not None and isinstance(
#         #         litellm_aws_region_name, str
#         #     ):
#         #         aws_region_name = litellm_aws_region_name

#         #     standard_aws_region_name = get_secret("AWS_REGION", None)
#         #     if standard_aws_region_name is not None and isinstance(
#         #         standard_aws_region_name, str
#         #     ):
#         #         aws_region_name = standard_aws_region_name

#         # if aws_region_name is None:
#         #     aws_region_name = "us-west-2"

#         if aws_region_name is None:
#             aws_region_name = "us-west-2"

#         credentials = super().get_credentials(
#             aws_access_key_id=aws_access_key_id,
#             aws_secret_access_key=aws_secret_access_key,
#             aws_session_token=aws_session_token,
#             aws_region_name=aws_region_name,
#             aws_session_name=aws_session_name,
#             aws_profile_name=aws_profile_name,
#             aws_role_name=aws_role_name,
#             aws_web_identity_token=aws_web_identity_token,
#             aws_sts_endpoint=aws_sts_endpoint,
#         )
#         # sigv4 = SigV4Auth(credentials, "bedrock", aws_region_name)

#         ### SET RUNTIME ENDPOINT ###
#         endpoint_url, proxy_endpoint_url = super().get_runtime_endpoint(
#             api_base=api_base,
#             aws_bedrock_runtime_endpoint=aws_bedrock_runtime_endpoint,
#             aws_region_name=aws_region_name,
#         )

#         if (stream is not None and stream is True) and provider != "ai21":
#             endpoint_url = f"{endpoint_url}/model/{modelId}/converse-stream"
#             proxy_endpoint_url = f"{proxy_endpoint_url}/model/{modelId}/converse-stream"
#         else:
#             endpoint_url = f"{endpoint_url}/model/{modelId}/converse"
#             proxy_endpoint_url = f"{proxy_endpoint_url}/model/{modelId}/converse"

#         _data = litellm.AmazonConverseConfig()._transform_request(
#             model=model,
#             messages=messages,
#             optional_params=optional_params,
#             litellm_params=litellm_params,
#         )

#         data = json.dumps(_data)

#         ## COMPLETION CALL

#         # headers = {"Content-Type": "application/json"}
#         # if extra_headers is not None:
#         #     headers = {"Content-Type": "application/json", **extra_headers}
#         # print(f"endpoint_url: {endpoint_url}, data: {data}, headers: {headers}")
#         # request = AWSRequest(
#         #     method="POST", url=endpoint_url, data=data, headers=headers
#         # )
#         # sigv4.add_auth(request)

#         # if (
#         #     extra_headers is not None and "Authorization" in extra_headers
#         # ):  # prevent sigv4 from overwriting the auth header
#         #     request.headers["Authorization"] = extra_headers["Authorization"]
#         # prepped = request.prepare()

#         # ## LOGGING
#         # logging_obj.pre_call(
#         #     input=messages,
#         #     api_key="",
#         #     additional_args={
#         #         "complete_input_dict": data,
#         #         "api_base": proxy_endpoint_url,
#         #         "headers": prepped.headers,
#         #     },
#         # )

#         return self.async_completion(
#             model=model,
#             messages=messages,
#             data=data,
#             api_base=proxy_endpoint_url,
#             model_response=model_response,
#             print_verbose=print_verbose,
#             encoding=encoding,
#             logging_obj=logging_obj,
#             optional_params=optional_params,
#             stream=False,
#             litellm_params=litellm_params,
#             logger_fn=logger_fn,
#             # headers=prepped.headers,
#             headers={"Authorization": "my-fake-key"},
#             timeout=timeout,
#             client=client,
#         )  # type: ignore
