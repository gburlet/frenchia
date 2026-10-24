from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer[dict[str, str]]):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class ErrorSerializer(serializers.Serializer[dict[str, str]]):
    detail = serializers.CharField()
