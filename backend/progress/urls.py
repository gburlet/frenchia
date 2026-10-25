from django.urls import path

from . import views

urlpatterns = [
    path("dashboard", views.DashboardView.as_view(), name="dashboard"),
    path("review", views.ReviewView.as_view(), name="review"),
    path("review/<int:review_id>", views.ReviewDetailView.as_view(), name="review-detail"),
    path("review/<int:review_id>/complete", views.ReviewCompleteView.as_view()),
]
