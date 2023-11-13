### INIT VARIABLES ###
import threading, requests
from typing import Callable, List, Optional, Dict, Union
from litellm.caching import Cache
import httpx
import json5
import requests

from litellm.caching import Cache

input_callback: List[Union[str, Callable]] = []
success_callback: List[Union[str, Callable]] = []
failure_callback: List[Union[str, Callable]] = []
callbacks: List[Callable] = []
set_verbose = False
email: Optional[
    str
] = None  # Not used anymore, will be removed in next MAJOR release - https://github.com/BerriAI/litellm/discussions/648
token: Optional[
    str
] = None  # Not used anymore, will be removed in next MAJOR release - https://github.com/BerriAI/litellm/discussions/648
telemetry = True
max_tokens = 256  # OpenAI Defaults
drop_params = False
retry = True
api_key: Optional[str] = None
openai_key: Optional[str] = None
azure_key: Optional[str] = None
anthropic_key: Optional[str] = None
replicate_key: Optional[str] = None
cohere_key: Optional[str] = None
maritalk_key: Optional[str] = None
ai21_key: Optional[str] = None
openrouter_key: Optional[str] = None
huggingface_key: Optional[str] = None
vertex_project: Optional[str] = None
vertex_location: Optional[str] = None
togetherai_api_key: Optional[str] = None
baseten_key: Optional[str] = None
aleph_alpha_key: Optional[str] = None
nlp_cloud_key: Optional[str] = None
use_client: bool = False
logging: bool = True
caching: bool = False # Not used anymore, will be removed in next MAJOR release - https://github.com/BerriAI/litellm/discussions/648
caching_with_models: bool = False  # # Not used anymore, will be removed in next MAJOR release - https://github.com/BerriAI/litellm/discussions/648
cache: Optional[Cache] = None # cache object <- use this - https://docs.litellm.ai/docs/caching
model_alias_map: Dict[str, str] = {}
max_budget: float = 0.0 # set the max budget across all providers
_current_cost = 0 # private variable, used if max budget is set 
error_logs: Dict = {}
add_function_to_prompt: bool = False # if function calling not supported by api, append function call details to system prompt
client_session: Optional[httpx.Client] = None
model_fallbacks: Optional[List] = None
model_cost_map_url: str = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
num_retries: Optional[int] = None
suppress_debug_info = False
#############################################

def get_model_cost_map(url: str):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if request is unsuccessful
        content = response.json()
        return content
    except:
        import importlib.resources
        import json
        with importlib.resources.open_text("litellm", "model_prices_and_context_window_backup.json") as f:
            content = json.load(f)
            return content
model_cost = get_model_cost_map(url=model_cost_map_url)
custom_prompt_dict:Dict[str, dict] = {}
####### THREAD-SPECIFIC DATA ###################
class MyLocal(threading.local):
    def __init__(self):
        self.user = "Hello World"


_thread_context = MyLocal()


def identify(event_details):
    # Store user in thread local data
    if "user" in event_details:
        _thread_context.user = event_details["user"]


####### ADDITIONAL PARAMS ################### configurable params if you use proxy models like Helicone, map spend to org id, etc.
api_base = None
headers = None
api_version = None
organization = None
config_path = None
####### Secret Manager #####################
secret_manager_client = None
####### COMPLETION MODELS ###################
open_ai_chat_completion_models: List = []
open_ai_text_completion_models: List = []
cohere_models: List = []
anthropic_models: List = []
openrouter_models: List = []
vertex_chat_models: List = []
vertex_code_chat_models: List = []
vertex_text_models: List = []
vertex_code_text_models: List = []
ai21_models: List = []
nlp_cloud_models: List = []
aleph_alpha_models: List = []
bedrock_models: List = []
deepinfra_models: List = []
perplexity_models: List = []
for key, value in model_cost.items():
    if value.get('litellm_provider') == 'openai':
        open_ai_chat_completion_models.append(key)
    elif value.get('litellm_provider') == 'text-completion-openai':
        open_ai_text_completion_models.append(key)
    elif value.get('litellm_provider') == 'cohere':
        cohere_models.append(key)
    elif value.get('litellm_provider') == 'anthropic':
        anthropic_models.append(key)
    elif value.get('litellm_provider') == 'openrouter':
        split_string = key.split('/', 1)
        openrouter_models.append(split_string[1])
    elif value.get('litellm_provider') == 'vertex_ai-text-models':
        vertex_text_models.append(key)
    elif value.get('litellm_provider') == 'vertex_ai-code-text-models':
        vertex_code_text_models.append(key)
    elif value.get('litellm_provider') == 'vertex_ai-chat-models':
        vertex_chat_models.append(key)
    elif value.get('litellm_provider') == 'vertex_ai-code-chat-models':
        vertex_code_chat_models.append(key)
    elif value.get('litellm_provider') == 'ai21':
        ai21_models.append(key)
    elif value.get('litellm_provider') == 'nlp_cloud':
        nlp_cloud_models.append(key)
    elif value.get('litellm_provider') == 'aleph_alpha':
        aleph_alpha_models.append(key)
    elif value.get('litellm_provider') == 'bedrock': 
        bedrock_models.append(key)
    elif value.get('litellm_provider') == 'deepinfra':
        deepinfra_models.append(key)
    elif value.get('litellm_provider') == 'perplexity':
        perplexity_models.append(key)

# known openai compatible endpoints - we'll eventually move this list to the model_prices_and_context_window.json dictionary
openai_compatible_endpoints: list = ["api.perplexity.ai"]


# well supported replicate llms
with open("config/models.json5") as json5_file:
    models_data = json5.load(json5_file)
    replicate_models: list = models_data["replicate_models"]
    huggingface_models: list = models_data["huggingface_models"]
    together_ai_models: list = models_data["together_ai_models"]
    baseten_models: list = models_data["baseten_models"]
    petals_models: list = models_data["petals_models"]
    ollama_models: list = models_data["ollama_models"]
    maritalk_models: list = models_data["maritalk_models"]
    provider_list: list = models_data["provider"]
    # mapping for those models which have larger equivalents
    longer_context_model_fallback_dict: dict = models_data[
        "longer_context_model_fallback_dict"
    ]

model_list = (
    open_ai_chat_completion_models
    + open_ai_text_completion_models
    + cohere_models
    + anthropic_models
    + replicate_models
    + openrouter_models
    + huggingface_models
    + vertex_chat_models
    + vertex_text_models
    + ai21_models
    + together_ai_models
    + baseten_models
    + aleph_alpha_models
    + nlp_cloud_models
    + ollama_models
    + bedrock_models
    + deepinfra_models
    + perplexity_models
    + maritalk_models
)

provider_list: List = [
    "openai",
    "custom_openai",
    "cohere",
    "anthropic",
    "replicate",
    "huggingface",
    "together_ai",
    "openrouter",
    "vertex_ai",
    "palm",
    "ai21",
    "baseten",
    "azure",
    "sagemaker",
    "bedrock",
    "vllm",
    "nlp_cloud",
    "petals",
    "oobabooga",
    "ollama",
    "deepinfra",
    "perplexity",
    "anyscale",
    "maritalk",
    "custom", # custom apis
]

models_by_provider: dict = {
    "openai": open_ai_chat_completion_models + open_ai_text_completion_models,
    "cohere": cohere_models,
    "anthropic": anthropic_models,
    "replicate": replicate_models,
    "huggingface": huggingface_models,
    "together_ai": together_ai_models,
    "baseten": baseten_models,
    "openrouter": openrouter_models,
    "vertex_ai": vertex_chat_models + vertex_text_models,
    "ai21": ai21_models,
    "bedrock": bedrock_models,
    "petals": petals_models,
    "ollama": ollama_models,
    "deepinfra": deepinfra_models,
    "perplexity": perplexity_models,
    "maritalk": maritalk_models
}

# mapping for those models which have larger equivalents 
longer_context_model_fallback_dict: dict = {
    # openai chat completion models
    "gpt-3.5-turbo": "gpt-3.5-turbo-16k", 
    "gpt-3.5-turbo-0301": "gpt-3.5-turbo-16k-0301", 
    "gpt-3.5-turbo-0613": "gpt-3.5-turbo-16k-0613", 
    "gpt-4": "gpt-4-32k", 
    "gpt-4-0314": "gpt-4-32k-0314", 
    "gpt-4-0613": "gpt-4-32k-0613", 
    # anthropic 
    "claude-instant-1": "claude-2", 
    "claude-instant-1.2": "claude-2",
    # vertexai
    "chat-bison": "chat-bison-32k",
    "chat-bison@001": "chat-bison-32k",
    "codechat-bison": "codechat-bison-32k", 
    "codechat-bison@001": "codechat-bison-32k",
    # openrouter 
    "openrouter/openai/gpt-3.5-turbo": "openrouter/openai/gpt-3.5-turbo-16k", 
    "openrouter/anthropic/claude-instant-v1": "openrouter/anthropic/claude-2",
}

####### EMBEDDING MODELS ###################

with open("config/embedding_model.json5") as json5_file:
    embedding_data = json5.load(json5_file)
    open_ai_embedding_models: list = embedding_data["open_ai_embedding_models"]
    cohere_embedding_models: list = embedding_data["cohere_embedding_models"]
    bedrock_embedding_models: list = embedding_data["bedrock_embedding_models"]

from .timeout import timeout
from .testing import *
from .utils import (
    client,
    exception_type,
    get_optional_params,
    modify_integration,
    token_counter,
    cost_per_token,
    completion_cost,
    get_litellm_params,
    Logging,
    acreate,
    get_model_list,
    get_max_tokens,
    register_prompt_template,
    validate_environment,
    check_valid_key,
    get_llm_provider,
    completion_with_config,
    register_model,
    encode, 
    decode
)
from .llms.huggingface_restapi import HuggingfaceConfig
from .llms.anthropic import AnthropicConfig
from .llms.replicate import ReplicateConfig
from .llms.cohere import CohereConfig
from .llms.ai21 import AI21Config
from .llms.together_ai import TogetherAIConfig
from .llms.palm import PalmConfig
from .llms.nlp_cloud import NLPCloudConfig
from .llms.aleph_alpha import AlephAlphaConfig
from .llms.petals import PetalsConfig
from .llms.vertex_ai import VertexAIConfig
from .llms.sagemaker import SagemakerConfig
from .llms.ollama import OllamaConfig
from .llms.maritalk import MaritTalkConfig
from .llms.bedrock import AmazonTitanConfig, AmazonAI21Config, AmazonAnthropicConfig, AmazonCohereConfig
from .llms.openai import OpenAIConfig, OpenAITextCompletionConfig
from .llms.azure import AzureOpenAIConfig
from .main import *  # type: ignore
from .integrations import *
from .exceptions import (
    AuthenticationError,
    InvalidRequestError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
    OpenAIError,
    ContextWindowExceededError,
    BudgetExceededError, 
    APIError,
)
from .budget_manager import BudgetManager
from .proxy.proxy_cli import run_server
from .router import Router
