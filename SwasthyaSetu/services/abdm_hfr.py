import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")


def get_abdm_config():
    """
    Reads ABDM configuration from the local .env file.
    No secret is hard-coded in the source code.
    """

    client_id = os.getenv("ABDM_CLIENT_ID")
    client_secret = os.getenv("ABDM_CLIENT_SECRET")
    base_url = os.getenv("ABDM_BASE_URL")

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "base_url": base_url
    }


def check_abdm_configuration():
    """
    Checks whether ABDM credentials have been configured locally.
    """

    config = get_abdm_config()

    if not config["base_url"]:
        return {
            "configured": False,
            "message": "ABDM base URL is not configured."
        }

    if not config["client_id"] or not config["client_secret"]:
        return {
            "configured": False,
            "message": (
                "ABDM API credentials are not configured yet. "
                "Official ABDM access/credentials are required "
                "before making authenticated HFR API requests."
            )
        }

    return {
        "configured": True,
        "message": "ABDM configuration is ready."
    }


if __name__ == "__main__":
    result = check_abdm_configuration()
    print(result)