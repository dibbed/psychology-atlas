"""Public JWT contract preserved, with server-side generation revocation from P00."""
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .cms_policy import policy_lock
from .cms_sessions import generation


class VersionedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        # Preserve SimpleJWT's user/password checks, joining generation in the existing user query.
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken(_("Token contained no recognizable user identification")) from exc
        try:
            user = self.user_model.objects.select_related("accountsecuritystate").get(**{api_settings.USER_ID_FIELD: user_id})
        except self.user_model.DoesNotExist as exc:
            raise AuthenticationFailed(_("User not found"), code="user_not_found") from exc
        if api_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")
        if api_settings.CHECK_REVOKE_TOKEN and validated_token.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password):
            raise AuthenticationFailed(_("The user's password has been changed."), code="password_changed")
        state = getattr(user, "accountsecuritystate", None)
        if validated_token.get("security_version", 0) != (state.security_version if state else 0):
            raise InvalidToken("Token has been revoked")
        return user


class VersionedRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        with policy_lock():
            token = super().for_user(user)
            token["security_version"] = generation(user.pk)
            return token


class VersionedTokenObtainPairSerializer(TokenObtainPairSerializer):
    token_class = VersionedRefreshToken


class VersionedTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        with policy_lock():
            token = self.token_class(attrs["refresh"])
            if token.get("security_version", 0) != generation(token.get("user_id")):
                raise InvalidToken("Token has been revoked")
            return super().validate(attrs)
