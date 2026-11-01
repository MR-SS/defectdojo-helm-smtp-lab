"""Run inside the local Django pod via manage.py shell, never on production.

Uses a temporary test user and restores the two global mail settings in finally.
Does not print passwords, session cookies or reset tokens.
"""
import json
import re
import secrets
import time
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from dojo.models import System_Settings
from dojo.notifications.models import Notifications
from dojo.notifications.tasks import async_create_notification

http = requests.Session()
http.trust_env = False
http.headers['Host'] = 'dojo.lab.local:8080'
mail = requests.Session()
mail.trust_env = False
base = 'http://defectdojo-django'
mailbase = 'http://mailpit:8025'
tag = 'smtp_local_' + secrets.token_hex(5)
address = tag + '@example.com'
password = 'Aa9!' + secrets.token_urlsafe(24)
new_password = 'Bb8!' + secrets.token_urlsafe(24)
U = get_user_model()
user = None
system = System_Settings.objects.get(no_cache=True)
old = {'email_from': system.email_from, 'enable_mail_notifications': system.enable_mail_notifications}
results = {'marker': tag, 'chart': '1.9.60', 'app': '3.4.202'}


def csrf(response):
    response.raise_for_status()
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.text)
    assert match, 'CSRF field missing'
    return match.group(1)


def inbox():
    r = mail.get(mailbase + '/api/v1/messages', timeout=5)
    r.raise_for_status()
    return r.json()['messages']


def await_message(predicate):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        for message in inbox():
            if any(item.get('Address') == address for item in message.get('To', [])) and predicate(message):
                detail = mail.get(mailbase + '/api/v1/message/' + message['ID'], timeout=5)
                detail.raise_for_status()
                return detail.json()
        time.sleep(1)
    raise AssertionError('Expected email did not arrive')


try:
    assert settings.EMAIL_HOST == 'mailpit' and settings.EMAIL_PORT == 1025
    assert settings.SITE_URL == 'http://dojo.lab.local:8080'
    user = U.objects.create_user(username=tag, email=address, password=password, is_active=True)
    system.email_from = 'dojo@example.com'
    system.enable_mail_notifications = True
    system.save(update_fields=['email_from', 'enable_mail_notifications'])

    form = http.get(base + '/password_reset/', timeout=15)
    submitted = http.post(base + '/password_reset/', data={'email': address, 'csrfmiddlewaretoken': csrf(form)}, allow_redirects=False, timeout=15)
    assert submitted.status_code == 302 and '/password_reset/done/' in submitted.headers.get('Location', ''), 'Password reset request failed'
    message = await_message(lambda m: 'password' in m['Subject'].lower())
    link = re.search(r'http://dojo\.lab\.local:8080/reset/[^\s<>]+', message['Text'])
    assert link, 'Reset email did not contain public siteUrl'
    reset_path = urlsplit(link.group()).path
    confirm = http.get(base + reset_path, allow_redirects=False, timeout=15)
    assert confirm.status_code == 302, 'Reset token was not accepted'
    form_path = urlsplit(confirm.headers['Location']).path
    form = http.get(base + form_path, timeout=15)
    completed = http.post(base + form_path, data={'new_password1': new_password, 'new_password2': new_password, 'csrfmiddlewaretoken': csrf(form)}, allow_redirects=False, timeout=15)
    if completed.status_code != 302:
        errors = re.findall(r'<ul[^>]*class="errorlist[^>]*>(.*?)</ul>', completed.text, re.S)
        print('RESET_FORM_ERRORS', [re.sub('<[^>]+>', '', error) for error in errors], 'STATUS', completed.status_code)
    assert completed.status_code == 302 and '/reset/done/' in completed.headers.get('Location', ''), 'New password rejected'
    user.refresh_from_db()
    assert user.check_password(new_password) and not user.check_password(password)
    login = http.get(base + '/login', timeout=15)
    logged_in = http.post(base + '/login', data={'username': tag, 'password': new_password, 'csrfmiddlewaretoken': csrf(login)}, allow_redirects=False, timeout=15)
    assert logged_in.status_code == 302, 'Login after reset failed'
    # Verify the session belongs to the test user, rather than trusting a redirect.
    from django.contrib.sessions.models import Session
    session_cookie = http.cookies.get(settings.SESSION_COOKIE_NAME)
    assert session_cookie
    session_data = Session.objects.get(session_key=session_cookie).get_decoded()
    assert session_data.get('_auth_user_id') == str(user.pk)
    results['password_reset'] = {'request': 'passed', 'public_link': 'passed', 'change_password': 'passed', 'http_login': 'passed'}

    prefs, _ = Notifications.objects.get_or_create(user=user, product=None)
    prefs.other = ['mail']
    prefs.save(update_fields=['other'])
    assert not async_create_notification.app.conf.task_always_eager, 'Celery eager mode would not test the worker'
    queued = async_create_notification.delay('other', recipients=[tag], title=tag, description='Local SMTP verification through the actual notification task', url='/')
    results['celery_task_id'] = queued.id
    delivered = await_message(lambda m: tag in m['Subject'])
    assert 'Local SMTP verification' in delivered['HTML']
    assert 'http://dojo.lab.local:8080http://' not in delivered['HTML'], 'Notification URL was double-prefixed'
    results['asynchronous_notification'] = 'received through broker and worker with user mail preference enabled'
    results['mailpit_total'] = mail.get(mailbase + '/api/v1/messages', timeout=5).json()['total']
    print('SMTP_E2E_RESULT ' + json.dumps(results, sort_keys=True))
finally:
    system = System_Settings.objects.get(no_cache=True)
    for key, value in old.items():
        setattr(system, key, value)
    system.save(update_fields=list(old))
    if user is not None:
        user.delete()
    http.close()
    mail.close()
    print('SMTP_E2E_CLEANUP temporary user removed; original mail settings restored')
