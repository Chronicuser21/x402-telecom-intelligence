from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any

class SipHeaderSchema(BaseModel):
    via: List[str] = Field(..., description="Ordered list of transaction Via routing branch paths.")
    to_field: str = Field(..., alias="to", description="Target destination URI identifier.")
    from_field: str = Field(..., alias="from", description="Originating user-agent parameter context.")
    call_id: str = Field(..., description="Cryptographically unique global call string transaction token.")
    cseq: str = Field(..., description="Sequence number tracking tracking field.")

class ForensicDecodePayload(BaseModel):
    method: str = Field(..., description="RFC 3261 standard method token (e.g. INVITE, CANCEL, BYE).")
    uri: str = Field(..., description="Parsed target uniform resource identifier target destination path.")
    headers: SipHeaderSchema = Field(..., description="Decompressed, case-insensitive structural header schema array mapping.")
    body: Optional[str] = Field(None, description="Optional raw Session Description Protocol block container string properties.")

class ToolCatalogResponse(BaseModel):
    status: str = Field("success", description="Global execution flag identifier descriptor context parameters.")
    schema_definition: Dict[str, Any] = Field(..., description="Dynamically extracted JSON schema profile boundary rules.")
