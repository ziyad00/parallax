"""Test fixture — Django models split across two apps."""

from django.db import models


class Profile(models.Model):
    pass


class Subscription(models.Model):
    pass
