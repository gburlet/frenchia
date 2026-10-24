from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import ErrorSerializer, LoginSerializer, UserSerializer

INVALID_CREDENTIALS = "Invalid username or password."


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(operation_id="auth_csrf", responses={204: None})
    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="auth_login",
        request=LoginSerializer,
        responses={200: UserSerializer, 400: ErrorSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        user = None
        if serializer.is_valid():
            user = authenticate(
                request,
                username=serializer.validated_data["username"],
                password=serializer.validated_data["password"],
            )
        if user is None:
            return Response({"detail": INVALID_CREDENTIALS}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="auth_logout", request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="auth_me", responses={200: UserSerializer})
    def get(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        return Response(UserSerializer(request.user).data)
