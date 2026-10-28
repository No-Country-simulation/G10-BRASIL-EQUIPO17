
import hashlib
import os
from pathlib import Path


class OCIStorage:
    def __init__(self, client, namespace: str, bucket: str):
        self.client = client
        self.namespace = namespace
        self.bucket = bucket

    @classmethod
    def from_environment(cls):
        import oci

        config_file = os.environ.get(
            "OCI_CONFIG_FILE",
            str(Path.home() / ".oci" / "config"),
        )
        profile = os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT")
        bucket = os.environ.get("OCI_BUCKET")

        if not bucket:
            raise ValueError("OCI_BUCKET não configurado")

        config = oci.config.from_file(
            file_location=config_file,
            profile_name=profile,
        )
        oci.config.validate_config(config)

        client = oci.object_storage.ObjectStorageClient(config)

        namespace = (
            os.environ.get("OCI_NAMESPACE")
            or client.get_namespace().data
        )

        return cls(client, namespace, bucket)

    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        if not object_name or not content:
            raise ValueError("Nome e conteúdo são obrigatórios")

        self.client.put_object(
            self.namespace,
            self.bucket,
            object_name,
            content,
            content_type=content_type,
        )

        return hashlib.sha256(content).hexdigest()

    def download_bytes(self, object_name: str) -> bytes:
        response = self.client.get_object(
            self.namespace,
            self.bucket,
            object_name,
        )

        return response.data.content
