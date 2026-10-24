from rest_framework import serializers


class SpeechRequestSerializer(serializers.Serializer[dict[str, object]]):
    text = serializers.CharField(max_length=2000)
    speed = serializers.FloatField(min_value=0.5, max_value=1.5, default=1.0)


class AudioClipSerializer(serializers.Serializer[dict[str, object]]):
    key = serializers.CharField()
    url = serializers.CharField()
    cached = serializers.BooleanField()


class InferenceErrorSerializer(serializers.Serializer[dict[str, str]]):
    detail = serializers.CharField()
    code = serializers.CharField()
