"""SAML 2.0 provider implementation."""

import base64
import secrets
import uuid
import zlib
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree as StdlibET

import defusedxml.ElementTree as ET
import structlog

from .models import IdentityProvider, SSOSession, SSOUserInfo
from .providers import BaseProvider

logger = structlog.get_logger()

# SAML XML Namespaces
SAML_NS = {
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
}


class SAMLProvider(BaseProvider):
    """SAML 2.0 identity provider implementation.

    Supports:
    - SP-initiated SSO
    - SAML assertions processing
    - Attribute mapping
    - SP metadata generation
    - Single Logout (SLO)
    """

    def __init__(self, idp: IdentityProvider, app_url: str):
        """Initialize the SAML provider.

        Args:
            idp: Identity provider with SAML settings
            app_url: Base URL of the application

        Raises:
            ValueError: If SAML settings are not configured
        """
        super().__init__(idp, app_url)

        if not idp.saml_settings:
            raise ValueError(f"SAML settings not configured for IdP {idp.id}")

        self.settings = idp.saml_settings

        # Set SP URLs if not configured
        if not self.settings.sp_entity_id:
            self.settings.sp_entity_id = (
                f"{self.app_url}/auth/sso/saml/metadata/{idp.tenant_id}"
            )

        if not self.settings.sp_acs_url:
            self.settings.sp_acs_url = (
                f"{self.app_url}/auth/sso/saml/acs/{idp.tenant_id}"
            )

        if not self.settings.sp_metadata_url:
            self.settings.sp_metadata_url = (
                f"{self.app_url}/auth/sso/saml/metadata/{idp.tenant_id}"
            )

    @staticmethod
    def create_session_for_auth(
        tenant_id: str,
        idp_id: str,
        relay_state: str | None = None,
    ) -> SSOSession:
        """Create an SSO session for SAML authentication.

        Args:
            tenant_id: Tenant ID
            idp_id: Identity provider ID
            relay_state: URL to return to after authentication

        Returns:
            A new SSO session ready for SAML flow
        """
        request_id = f"_id{uuid.uuid4().hex}"

        session = SSOSession(
            tenant_id=tenant_id,
            idp_id=idp_id,
            relay_state=relay_state,
            saml_request_id=request_id,
        )

        logger.debug(
            "saml_session_created",
            session_id=session.id,
            tenant_id=tenant_id,
            idp_id=idp_id,
            request_id=request_id,
        )

        return session

    def _build_authn_request(
        self, request_id: str, relay_state: str | None = None
    ) -> str:
        """Build a SAML AuthnRequest XML document.

        Args:
            request_id: Unique request ID
            relay_state: Optional relay state

        Returns:
            XML string of the AuthnRequest
        """
        now = datetime.utcnow()
        issue_instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build AuthnRequest
        authn_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                    ID="{request_id}"
                    Version="2.0"
                    IssueInstant="{issue_instant}"
                    Destination="{self.settings.idp_sso_url}"
                    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                    AssertionConsumerServiceURL="{self.settings.sp_acs_url}">
    <saml:Issuer>{self.settings.sp_entity_id}</saml:Issuer>
    <samlp:NameIDPolicy Format="{self.settings.name_id_format}"
                        AllowCreate="true"/>
</samlp:AuthnRequest>"""

        return authn_request

    def _encode_request(self, xml_request: str, use_deflate: bool = True) -> str:
        """Encode a SAML request for HTTP-Redirect binding.

        Args:
            xml_request: XML string to encode
            use_deflate: Whether to use DEFLATE compression

        Returns:
            Base64-encoded request string
        """
        if use_deflate:
            # Deflate and base64 encode
            compressed = zlib.compress(xml_request.encode("utf-8"))[
                2:-4
            ]  # Strip zlib header/checksum
            encoded = base64.b64encode(compressed).decode("utf-8")
        else:
            encoded = base64.b64encode(xml_request.encode("utf-8")).decode("utf-8")

        return encoded

    def generate_auth_request(self, session: SSOSession) -> str:
        """Generate a SAML AuthnRequest redirect URL.

        Args:
            session: SSO session with request ID

        Returns:
            URL to redirect the user to for SAML authentication
        """
        # Build AuthnRequest XML
        authn_request = self._build_authn_request(
            request_id=session.saml_request_id,
            relay_state=session.relay_state,
        )

        # Encode for HTTP-Redirect
        encoded_request = self._encode_request(authn_request)

        # Build redirect URL
        params = {
            "SAMLRequest": encoded_request,
        }

        if session.relay_state:
            params["RelayState"] = session.state  # Use session state as RelayState

        auth_url = f"{self.settings.idp_sso_url}?{urlencode(params)}"

        logger.debug(
            "saml_auth_request_generated",
            idp_id=self.idp.id,
            request_id=session.saml_request_id,
        )

        return auth_url

    async def generate_auth_url(self, session: SSOSession) -> str:
        """Generate the SAML authentication URL (alias for generate_auth_request).

        Args:
            session: SSO session with request ID

        Returns:
            URL to redirect the user to for authentication
        """
        return self.generate_auth_request(session)

    def _parse_saml_response(self, saml_response: str) -> ET.Element:
        """Parse and decode a SAML response.

        Args:
            saml_response: Base64-encoded SAML response

        Returns:
            Parsed XML Element
        """
        # Decode base64
        try:
            decoded = base64.b64decode(saml_response)
            xml_str = decoded.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to decode SAML response: {e}")

        # Parse XML
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse SAML response XML: {e}")

        return root

    def _validate_response(
        self,
        root: ET.Element,
        expected_request_id: str | None = None,
    ) -> None:
        """Validate a SAML response.

        Args:
            root: Parsed XML root element
            expected_request_id: Expected InResponseTo value

        Raises:
            ValueError: If validation fails
        """
        # Check response status
        status_elem = root.find(".//samlp:StatusCode", SAML_NS)
        if status_elem is not None:
            status_code = status_elem.get("Value", "")
            if "Success" not in status_code:
                status_msg = root.find(".//samlp:StatusMessage", SAML_NS)
                msg = status_msg.text if status_msg is not None else "Unknown error"
                raise ValueError(f"SAML authentication failed: {msg}")

        # Validate InResponseTo if we have an expected request ID
        if expected_request_id:
            in_response_to = root.get("InResponseTo")
            if in_response_to and in_response_to != expected_request_id:
                raise ValueError(
                    f"Invalid InResponseTo: {in_response_to} != {expected_request_id}"
                )

        # Note: In production, also validate:
        # - XML signature
        # - Assertion conditions (NotBefore, NotOnOrAfter)
        # - Audience restriction
        # - Issuer matches expected IdP

    def _extract_attributes(self, root: ET.Element) -> dict[str, Any]:
        """Extract attributes from a SAML assertion.

        Args:
            root: Parsed XML root element

        Returns:
            Dictionary of attribute name -> value(s)
        """
        attributes = {}

        # Find all Attribute elements
        for attr_elem in root.findall(".//saml:Attribute", SAML_NS):
            name = attr_elem.get("Name")
            if not name:
                continue

            # Get all values
            values = []
            for value_elem in attr_elem.findall("saml:AttributeValue", SAML_NS):
                if value_elem.text:
                    values.append(value_elem.text)

            # Store as single value or list
            if len(values) == 1:
                attributes[name] = values[0]
            elif len(values) > 1:
                attributes[name] = values

        return attributes

    def _get_name_id(self, root: ET.Element) -> str | None:
        """Extract the NameID from a SAML assertion.

        Args:
            root: Parsed XML root element

        Returns:
            NameID value or None
        """
        name_id_elem = root.find(".//saml:NameID", SAML_NS)
        if name_id_elem is not None and name_id_elem.text:
            return name_id_elem.text
        return None

    def process_response(
        self,
        saml_response: str,
        expected_request_id: str | None = None,
    ) -> SSOUserInfo:
        """Process a SAML response and extract user information.

        Args:
            saml_response: Base64-encoded SAML response from IdP
            expected_request_id: Expected InResponseTo value for validation

        Returns:
            SSOUserInfo with user data from the assertion

        Raises:
            ValueError: If response is invalid or validation fails
        """
        # Parse response
        root = self._parse_saml_response(saml_response)

        # Validate response
        self._validate_response(root, expected_request_id)

        # Extract attributes
        attributes = self._extract_attributes(root)

        # Get NameID
        name_id = self._get_name_id(root)

        logger.debug(
            "saml_response_processed",
            idp_id=self.idp.id,
            name_id=name_id,
            attributes=list(attributes.keys()),
        )

        # Map attributes to user info
        return self._map_attributes_to_user(name_id, attributes)

    async def process_response(
        self,
        response_data: dict[str, Any],
        session: SSOSession,
    ) -> SSOUserInfo:
        """Process the SAML response (async interface for BaseProvider).

        Args:
            response_data: Dict with 'SAMLResponse' from ACS
            session: SSO session for validation

        Returns:
            User information extracted from assertion
        """
        saml_response = response_data.get("SAMLResponse")
        if not saml_response:
            raise ValueError("No SAMLResponse in response data")

        # Use the sync method
        return self.process_response(
            saml_response=saml_response,
            expected_request_id=session.saml_request_id,
        )

    def _map_attributes_to_user(
        self,
        name_id: str | None,
        attributes: dict[str, Any],
    ) -> SSOUserInfo:
        """Map SAML attributes to SSOUserInfo.

        Args:
            name_id: SAML NameID
            attributes: Extracted SAML attributes

        Returns:
            SSOUserInfo with mapped attributes

        Raises:
            ValueError: If required attributes are missing
        """
        mapping = self.settings.attribute_mapping

        # Get email (required)
        email = None
        email_attr = mapping.get("email")
        if email_attr and email_attr in attributes:
            email = attributes[email_attr]

        # Try common email attribute names
        if not email:
            for attr_name in [
                "email",
                "Email",
                "emailAddress",
                "mail",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
            ]:
                if attr_name in attributes:
                    email = attributes[attr_name]
                    break

        # Fall back to NameID if it looks like an email
        if not email and name_id and "@" in name_id:
            email = name_id

        if not email:
            raise ValueError("No email found in SAML assertion")

        # Get subject (prefer NameID)
        subject_id = name_id or email

        # Get optional attributes
        def get_attr(key: str) -> str | None:
            attr_name = mapping.get(key)
            if attr_name and attr_name in attributes:
                val = attributes[attr_name]
                return val if isinstance(val, str) else val[0] if val else None
            return None

        name = get_attr("name")
        first_name = get_attr("first_name")
        last_name = get_attr("last_name")

        # Build full name if we have parts
        if not name and first_name and last_name:
            name = f"{first_name} {last_name}"

        # Get groups (may be a list)
        groups_attr = mapping.get("groups")
        groups = []
        if groups_attr and groups_attr in attributes:
            groups_val = attributes[groups_attr]
            if isinstance(groups_val, list):
                groups = groups_val
            elif groups_val:
                groups = [groups_val]

        return SSOUserInfo(
            subject_id=str(subject_id),
            email=email,
            email_verified=True,  # SAML assertions are trusted
            name=name,
            first_name=first_name,
            last_name=last_name,
            groups=groups,
            raw_attributes=attributes,
        )

    def generate_metadata(
        self,
        sp_cert: str | None = None,
        want_assertions_signed: bool | None = None,
        want_messages_signed: bool | None = None,
    ) -> str:
        """Generate SP metadata XML.

        Args:
            sp_cert: SP certificate (PEM format) for signing
            want_assertions_signed: Override want assertions signed setting
            want_messages_signed: Override want messages signed setting

        Returns:
            SP metadata XML string
        """
        want_signed = (
            want_assertions_signed
            if want_assertions_signed is not None
            else self.settings.want_assertions_signed
        )
        want_msg_signed = (
            want_messages_signed
            if want_messages_signed is not None
            else self.settings.want_messages_signed
        )

        # Build metadata XML
        metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
                     entityID="{self.settings.sp_entity_id}">
    <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
                        WantAssertionsSigned="{"true" if want_signed else "false"}"
                        AuthnRequestsSigned="{"true" if self.settings.authn_requests_signed else "false"}">
        <md:NameIDFormat>{self.settings.name_id_format}</md:NameIDFormat>
        <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                     Location="{self.settings.sp_acs_url}"
                                     index="0"
                                     isDefault="true"/>
    </md:SPSSODescriptor>
</md:EntityDescriptor>"""

        logger.debug(
            "saml_metadata_generated",
            idp_id=self.idp.id,
            entity_id=self.settings.sp_entity_id,
        )

        return metadata

    def handle_logout(
        self,
        session_index: str | None = None,
        name_id: str | None = None,
    ) -> str | None:
        """Generate a logout request URL if SLO is configured.

        Args:
            session_index: SAML session index
            name_id: User's NameID

        Returns:
            Logout URL or None if SLO not configured
        """
        if not self.settings.idp_slo_url:
            return None

        request_id = f"_id{uuid.uuid4().hex}"
        now = datetime.utcnow()
        issue_instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build LogoutRequest
        name_id_xml = f"<saml:NameID>{name_id}</saml:NameID>" if name_id else ""
        session_index_xml = (
            f"<samlp:SessionIndex>{session_index}</samlp:SessionIndex>"
            if session_index
            else ""
        )

        logout_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                     xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                     ID="{request_id}"
                     Version="2.0"
                     IssueInstant="{issue_instant}"
                     Destination="{self.settings.idp_slo_url}">
    <saml:Issuer>{self.settings.sp_entity_id}</saml:Issuer>
    {name_id_xml}
    {session_index_xml}
</samlp:LogoutRequest>"""

        # Encode and build URL
        encoded_request = self._encode_request(logout_request)
        params = {"SAMLRequest": encoded_request}

        logout_url = f"{self.settings.idp_slo_url}?{urlencode(params)}"

        logger.debug(
            "saml_logout_request_generated",
            idp_id=self.idp.id,
            request_id=request_id,
        )

        return logout_url
