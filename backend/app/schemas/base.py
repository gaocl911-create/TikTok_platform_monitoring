from datetime import UTC, datetime

from pydantic import BaseModel, field_serializer


class UtcResponseModel(BaseModel):
    """Serialize database-naive UTC timestamps with an explicit UTC offset."""

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_utc_datetime(self, value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return value
