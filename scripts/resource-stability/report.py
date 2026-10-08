"""Fail-closed evidence evaluation; thresholds come from the frozen run manifest."""
from __future__ import annotations

import math
import statistics

ROLES = ('rch', 'daemon')
OOM_FIELDS = ('oom', 'oom_kill', 'oom_group_kill')


def number(value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'expected finite number >= {minimum}: {value!r}')
    return value


def validate(samples, criteria, traffic, shutdown):
    duration = number(criteria['duration_s'], 1)
    if number(criteria['warmup_s']) >= duration:
        raise ValueError('warmup must end before observation')
    number(criteria['sample_interval_s'], 0.01)
    number(criteria['traffic_window_s'], 0.01)
    for role in ROLES:
        for key in ('max_slope_mib_per_minute', 'max_growth_mib', 'max_rss_plus_swap_mib',
                    'max_fd_growth', 'max_thread_growth'):
            number(criteria[role][key])
        if not isinstance(shutdown[role]['graceful'], bool):
            raise ValueError('shutdown outcome must be explicit')
    if not isinstance(traffic['fixture_qualified'], bool):
        raise ValueError('fixture qualification must be explicit')
    for key in ('expected_messages', 'verified_messages', 'poll_progress', 'poll_errors', 'http_errors'):
        number(traffic[key])
    if not samples or not traffic['windows']:
        raise ValueError('samples and continuing traffic windows required')
    for window in traffic['windows']:
        for key in ('start_s', 'end_s', 'expected_messages', 'verified_messages', 'poll_progress', 'poll_errors', 'http_errors'):
            number(window[key])
        if window['end_s'] <= window['start_s']:
            raise ValueError('traffic windows must have positive duration')
    for row in samples:
        number(row['elapsed_s'])
        for role in ROLES:
            value = row[role]
            for field in ('rss_plus_swap_bytes', 'private_plus_swap_bytes', 'anonymous_plus_swap_bytes'):
                number(value[field])
            number(value['process_start_ticks'], 1)
            number(value['fds'])
            number(value['status_kib']['Threads'], 1)
            for key in OOM_FIELDS:
                number(value['cgroup']['memory_events'][key])


def slope(points: list[tuple[float, float]]) -> float:
    """Least-squares bytes/second. Raw samples and window medians remain in evidence."""
    mean_x = statistics.mean(x for x, _ in points)
    mean_y = statistics.mean(y for _, y in points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if not denominator:
        raise ValueError('Distinct sample times required')
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator


def evaluate(samples: list[dict], criteria: dict, traffic: dict, shutdown: dict) -> dict:
    try:
        validate(samples, criteria, traffic, shutdown)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return {'passed': False, 'failures': [f'incomplete or malformed evidence: {error}'], 'roles': {}}
    failures = []
    elapsed = samples[-1]['elapsed_s']
    if elapsed < criteria['duration_s']:
        failures.append('observation shorter than frozen duration')
    times = [row['elapsed_s'] for row in samples]
    if times[0] > criteria['sample_interval_s'] or any(
            later <= earlier or later - earlier > 1.5 * criteria['sample_interval_s']
            for earlier, later in zip(times, times[1:])):
        failures.append('sampling gap or invalid time order')
    if not traffic['fixture_qualified']:
        failures.append('fixture did not survive operational qualification')
    if traffic['expected_messages'] <= 0 or traffic['verified_messages'] != traffic['expected_messages']:
        failures.append('unique message delivery incomplete or absent')
    if traffic['poll_errors'] or traffic['http_errors']:
        failures.append('poll or HTTP errors')
    if traffic['poll_progress'] <= 0:
        failures.append('event polling made no progress')
    windows = traffic['windows']
    previous_end = 0
    for window in windows:
        if (abs(window['start_s'] - previous_end) > criteria['sample_interval_s']
                or window['end_s'] - window['start_s'] > criteria['traffic_window_s']
                or window['expected_messages'] <= 0 or window['verified_messages'] != window['expected_messages']
                or window['poll_progress'] <= 0 or window['poll_errors'] or window['http_errors']):
            failures.append('traffic stopped, failed or has an unobserved interval')
            break
        previous_end = window['end_s']
    if previous_end < criteria['duration_s'] - criteria['sample_interval_s']:
        failures.append('traffic does not cover full observation')
    for key in ('expected_messages', 'verified_messages', 'poll_progress', 'poll_errors', 'http_errors'):
        if sum(window[key] for window in windows) != traffic[key]:
            failures.append(f'traffic total inconsistent: {key}')
    if any(not shutdown[role]['graceful'] for role in ROLES):
        failures.append('service shutdown was not graceful')
    roles = {}
    for role in ROLES:
        lifetime = [row[role] for row in samples]
        if len({value['process_start_ticks'] for value in lifetime}) != 1:
            failures.append(f'{role}: process restarted')
        oom = any(value['cgroup']['memory_events'][key] > 0
                  for value in lifetime for key in OOM_FIELDS)
        if oom:
            failures.append(f'{role}: OOM during service lifetime')
        steady = [(row['elapsed_s'], row[role]) for row in samples
                  if row['elapsed_s'] >= criteria['warmup_s']]
        if len(steady) < 6:
            failures.append(f'{role}: insufficient post-warmup samples')
            continue
        points = [(t, value['rss_plus_swap_bytes']) for t, value in steady]
        trend = slope(points) * 60 / 1048576
        quarter = max(1, len(points) // 4)
        growth = (statistics.median(value for _, value in points[-quarter:])
                  - statistics.median(value for _, value in points[:quarter])) / 1048576
        peak = max(value['rss_plus_swap_bytes'] for value in lifetime) / 1048576
        fd_growth = max(value['fds'] for _, value in steady) - steady[0][1]['fds']
        thread_growth = max(value['status_kib']['Threads'] for _, value in steady) - steady[0][1]['status_kib']['Threads']
        limit = criteria[role]
        roles[role] = {'rss_plus_swap_peak_mib': peak, 'slope_mib_per_minute': trend,
                       'last_vs_first_quarter_median_growth_mib': growth,
                       'fd_growth': fd_growth, 'thread_growth': thread_growth, 'oom': oom}
        accounting = {}
        for field in ('rss_plus_swap_bytes', 'private_plus_swap_bytes', 'anonymous_plus_swap_bytes'):
            series = [(t, value[field]) for t, value in steady]
            field_slope = slope(series) * 60 / 1048576
            field_growth = (statistics.median(v for _, v in series[-quarter:])
                            - statistics.median(v for _, v in series[:quarter])) / 1048576
            accounting[field] = {'slope_mib_per_minute': field_slope, 'median_growth_mib': field_growth}
            if field_slope > limit['max_slope_mib_per_minute'] or field_growth > limit['max_growth_mib']:
                failures.append(f'{role}: growing memory-plus-swap trend')
        roles[role]['accounting_trends'] = accounting
        if peak > limit['max_rss_plus_swap_mib']:
            failures.append(f'{role}: memory budget exceeded')
        if fd_growth > limit['max_fd_growth'] or thread_growth > limit['max_thread_growth']:
            failures.append(f'{role}: thread or descriptor growth')
    return {'passed': not failures, 'failures': failures, 'observed_s': elapsed, 'roles': roles}
