import os

def delete_from_inbox(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)