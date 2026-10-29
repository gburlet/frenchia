from django.urls import path

from . import views

urlpatterns = [
    path("vocab/sets", views.SetListView.as_view(), name="vocab-sets"),
    path("vocab/sets/<slug:slug>", views.SetDetailView.as_view(), name="vocab-set"),
    path("vocab/sets/<slug:slug>/learn", views.LearnSetView.as_view(), name="vocab-set-learn"),
    path("vocab/sets/<slug:slug>/remove", views.RemoveSetView.as_view(), name="vocab-set-remove"),
    path("vocab/words/<int:lexeme_id>/add", views.AddWordView.as_view(), name="vocab-word-add"),
    path(
        "vocab/words/<int:lexeme_id>/remove",
        views.RemoveLexemeView.as_view(),
        name="vocab-word-remove",
    ),
    path("vocab/review", views.QueueView.as_view(), name="vocab-queue"),
    path("vocab/cards/<int:card_id>/check", views.CheckView.as_view(), name="vocab-check"),
    path("vocab/cards/<int:card_id>/remove", views.RemoveWordView.as_view(), name="vocab-remove"),
    path("vocab/cards/<int:card_id>/review", views.ReviewView.as_view(), name="vocab-review"),
]
