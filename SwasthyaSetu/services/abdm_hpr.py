import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")


def get_abdm_hpr_config():
    """
    Reads ABDM HPR configuration from the local .env file.
    """

    client_id = os.getenv("ABDM_CLIENT_ID")
    client_secret = os.getenv("ABDM_CLIENT_SECRET")
    base_url = os.getenv("ABDM_BASE_URL")

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "base_url": base_url
    }


def check_hpr_configuration():
    """
    Checks whether the required ABDM configuration exists.
    """

    config = get_abdm_hpr_config()

    if not config["base_url"]:
        return {
            "configured": False,
            "message": "ABDM base URL is not configured."
        }

    if not config["client_id"] or not config["client_secret"]:
        return {
            "configured": False,
            "message": (
                "ABDM HPR credentials are not configured yet. "
                "Official ABDM access is required before "
                "authenticated HPR requests can be made."
            )
        }

    return {
        "configured": True,
        "message": "ABDM HPR configuration is ready."
    }


if __name__ == "__main__":
    result = check_hpr_configuration()
    print(result)