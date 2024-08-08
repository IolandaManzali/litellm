import os
import sys
import traceback

from dotenv import load_dotenv

load_dotenv()
import os

sys.path.insert(
    0, os.path.abspath("../..")
)  # Adds the parent directory to the system path
import openai
import pytest

import litellm
from litellm import (
    AuthenticationError,
    BadRequestError,
    OpenAIError,
    RateLimitError,
    ServiceUnavailableError,
    completion,
    completion_with_retries,
)

user_message = "Hello, whats the weather in San Francisco??"
messages = [{"content": user_message, "role": "user"}]


def logger_fn(user_model_dict):
    # print(f"user_model_dict: {user_model_dict}")
    pass


# completion with num retries + impact on exception mapping
def test_completion_with_num_retries():
    try:
        bad_messages = [{"messages": "vibe", "bad": "message"}]
        response = completion(
            model="j2-ultra",
            messages=bad_messages,
            num_retries=2,
        )
        pytest.fail(
            "This should not have passed. Invalid message={}, was sent.".format(
                bad_messages
            )
        )
    except Exception:
        pass


# test_completion_with_num_retries()
def test_completion_with_0_num_retries():
    try:
        litellm.set_verbose = False
        print("making request")

        # Use the completion function
        response = completion(
            model="gpt-3.5-turbo",
            messages=[{"gm": "vibe", "role": "user"}],
            max_retries=4,
        )

        print(response)

        # print(response)
    except Exception as e:
        print("exception", e)
        pass
