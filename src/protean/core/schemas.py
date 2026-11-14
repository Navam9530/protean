from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """API models speak camelCase (what the UI uses) and accept snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
