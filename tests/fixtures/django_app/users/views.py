"""Two views computing the same join — should cluster together."""

from .models import Profile, Subscription
from billing.models import Invoice


def user_dashboard(request, user_id):
    profile = Profile.objects.get(pk=user_id)
    subs = Subscription.objects.filter(profile=profile)
    invs = Invoice.objects.filter(profile=profile)
    return profile, subs, invs


def user_summary(request, user_id):
    p = Profile.objects.select_related("subscription").get(pk=user_id)
    invoices = Invoice.objects.filter(user_id=p.id)
    sub = Subscription.objects.filter(user_id=p.id).first()
    return {"p": p, "invoices": invoices, "sub": sub}


def unrelated_lookup(request):
    return Profile.objects.all()
