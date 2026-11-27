from pydantic import Field

from protean import config
from protean.core.schemas import CamelModel
from protean.modules.families.licenses import License


class PublishRequest(CamelModel):
    """Only what the user changed. A field that is left out keeps what the repo has; on a first
    publish the README and license fall back to the family folder's own files (a README may be
    empty) and the description stays empty."""

    description: str | None = Field(
        default=None, max_length=350
    )  # the repo's About text
    license: License | None = None
    readme: str | None = Field(default=None, max_length=config.MAX_README_CHARS)


class PublishForm(CamelModel):
    """What the publish form starts from, read from the saved family's folder."""

    description: str  # the About text last sent; "" before the first publish
    readme: str
    license: str | None  # "mit", "apache-2.0", "other"; None when there is no LICENSE
