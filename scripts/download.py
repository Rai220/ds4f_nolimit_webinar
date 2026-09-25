"""Run inside the pinned image; downloads only the fixed model revision."""
import os
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id=os.environ['MODEL_REPO'],
    revision=os.environ['MODEL_REVISION'],
    local_dir='/data/model',
)
