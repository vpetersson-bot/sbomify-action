#!/usr/bin/env python3
"""Check the tag classifier against the cases that caught it out.

Run before spending an hour of API calls and ten of compute on the result.
Every "should reject" here is a ref the previous resolver actually produced.
"""

import sys

sys.path.insert(0, "/home/ubuntu/sbomify-eval")
from resolve_releases import _is_release_tag, _sort_key  # noqa: E402

ACCEPT = [
    ("v2.34.2", "psf/requests"),
    ("2.34.2", "psf/requests"),
    ("v19.2.8", "facebook/react"),
    ("5.12.0", "Alamofire/Alamofire"),
    # Project-name prefixes, which are these projects' own conventions.
    ("curl-8_21_0", "curl/curl"),
    ("camel-4.22.0", "apache/camel"),
    ("druid-37.0.0", "apache/druid"),
    ("dubbo-3.2.20", "apache/dubbo"),
    ("clojure-1.12.5", "clojure/clojure"),
    ("OTP-29.0.5", "erlang/otp"),
    ("zookeeper-3.9.4", "apache/zookeeper"),
    # Generic prefixes. Rejecting these left Hadoop on a 2011 release
    # candidate and ZooKeeper on 2.2.1 while it ships 3.9.x.
    ("release-3.9.4", "apache/zookeeper"),
    ("rel/release-3.4.1", "apache/hadoop"),
    ("releases/lucene/10.5.0", "apache/lucene"),
    ("v1.7.21", "phoenixframework/phoenix"),
    # A suffix that means "final", not "prerelease".
    ("netty-4.2.17.Final", "netty/netty"),
    ("3.2.1.RELEASE", "spring-projects/spring-framework"),
]

REJECT = [
    # Tags the old resolver returned. Every one of these was going to be
    # scanned as if it were the project's release.
    ("show", "apache/kafka"),
    ("remove-ozone", "apache/hadoop"),
    ("assets", "Mic92/sops-nix"),
    ("zookeeper-", "apache/zookeeper"),
    ("stable/5.1.x", "django/django"),
    # Sub-package tags in monorepos: a release of something, not of this.
    ("meta-v1.3.0-nullsafety.2", "dart-lang/sdk"),
    ("xdg_directories-v1.1.0", "flutter/packages"),
    ("web_socket_channel-v3.0.3", "dart-lang/http"),
    ("bloc_lint-v0.4.2", "felangel/bloc"),
    ("desktop-v0.60.99", "PostHog/posthog"),
    ("sea-orm-cli@2.0.1", "SeaQL/sea-orm"),
    # Prereleases.
    ("autogpt-platform-beta-v0.7.0", "Significant-Gravitas/AutoGPT"),
    ("v2.0.0-rc.1", "psf/requests"),
    ("v1.0.0-nightly", "psf/requests"),
    # Compact prereleases, welded to the number. Django tags alphas this way,
    # and the digits alone sort 6.1a1 above every 6.0.x release.
    ("6.1a1", "django/django"),
    ("6.1b1", "django/django"),
    ("6.1rc1", "django/django"),
    ("0.92RC0", "apache/hadoop"),
    ("3.14.0-110.0.dev", "dart-lang/sdk"),
    ("v1.0.0-preview3", "dotnet/runtime"),
    # A wildcard is a maintenance branch, not a release.
    ("stable/5.1.x", "django/django"),
    ("5.1.x", "django/django"),
]

fails = 0
for tag, repo in ACCEPT:
    if not _is_release_tag(tag, repo):
        print(f"  SHOULD ACCEPT but rejected: {repo:32s} {tag}")
        fails += 1
for tag, repo in REJECT:
    if _is_release_tag(tag, repo):
        print(f"  SHOULD REJECT but accepted: {repo:32s} {tag}")
        fails += 1

# Ordering: the newest must win, including across digit-count boundaries.
ORDER = [
    (["v1.9.0", "v1.10.0", "v1.2.0"], "v1.10.0"),
    (["curl-8_9_0", "curl-8_21_0"], "curl-8_21_0"),
    (["OTP-27.0", "OTP-29.0.5"], "OTP-29.0.5"),
    (["v1.5.3", "v1.7.21"], "v1.7.21"),  # the Phoenix case
]
for tags, expected in ORDER:
    got = max(tags, key=_sort_key)
    if got != expected:
        print(f"  WRONG ORDER: {tags} -> {got}, expected {expected}")
        fails += 1



# Cases found by auditing the resolved list rather than by guessing: each one
# outranked a real version under numeric comparison.
DATES = [
    ("release-1434511043", "minio"),        # a 2015 unix timestamp
    ("release-20230510.1905", "tigerbeetle"),  # a 2023 date
    ("release-09.11.1", "batteries-included"),  # 2009; semver has no "09"
    ("20240101", "someproject"),
]
for tag, repo in DATES:
    if _is_release_tag(tag, repo):
        print(f"  SHOULD REJECT (date/timestamp): {repo:24s} {tag}")
        fails += 1

# Maven's aggregator for the same project, not a different package.
if not _is_release_tag("gson-parent-2.9.1", "gson"):
    print("  SHOULD ACCEPT: gson/gson-parent-2.9.1")
    fails += 1
# ...but a genuinely different package still must not pass.
if _is_release_tag("sea-orm-cli@2.0.1", "sea-orm"):
    print("  SHOULD REJECT: sea-orm/sea-orm-cli@2.0.1")
    fails += 1

# Ordering with the new rejections in place.
if max(["v3.9.0", "v3.8.0"], key=_sort_key) != "v3.9.0":
    print("  WRONG ORDER for batteries-included")
    fails += 1

print(f"\n{fails} failure(s)" if fails else "\nall cases pass (including the audit findings)")
sys.exit(1 if fails else 0)
