"""Small opt-in text summaries; JSON interfaces remain unchanged."""
from __future__ import annotations


def _safe(value, limit=160):
    return ''.join(c if c.isprintable() else '?' for c in str(value))[:limit]


def status(value, language='ru'):
    ru = language == 'ru'
    if value.get('dry_run'):
        return (('Проверка плана: без исполнения\nСтадии: ' if ru else 'Plan preview: no execution\nStages: ')
                + ' -> '.join(value.get('stages', []))
                + ('\nВызовы моделей: 0' if ru else '\nModel calls: 0'))
    labels = {'pending': 'ожидает', 'running': 'выполняется', 'completed': 'завершён',
              'paused': 'пауза', 'failed': 'ошибка', 'cancelled': 'отменён',
              'succeeded': 'готово', 'interrupted': 'прервано'}
    label = lambda name: labels.get(name, name) if ru else name
    lines = [('Workflow: ' if not ru else 'Workflow: ') + _safe(value.get('workflow_id', '-')),
             ('Состояние: ' if ru else 'State: ') + _safe(label(value.get('state', 'unknown')))]
    for name, node in value.get('stages', {}).items():
        lines.append('  ' + _safe(name, 24) + ': ' + _safe(label(node.get('state', 'pending')), 24)
                     + ('; попыток ' if ru else '; attempts ') + _safe(node.get('attempts', 0), 8))
    lines.append(('Запросы: ' if ru else 'Requests: ') + _safe(value.get('requests_used', '?'), 8)
                 + (' использовано, осталось ' if ru else ' used, remaining ') + _safe(value.get('requests_remaining', '?'), 8))
    seconds = value.get('active_time_remaining_s')
    remaining = f'{seconds:.1f}' if type(seconds) in (int, float) else '?'
    lines.append(('Активное время: осталось ' if ru else 'Active time remaining: ') + remaining + ' s')
    lines.append(('Принят сохранённый результат: ' if ru else 'Accepted saved snapshot: ') + ('yes' if value.get('accepted') is True else 'no'))
    if value.get('integrity') == 'failed':
        lines.append('Целостность результата нарушена; приёмка недействительна.' if ru else 'Result integrity failed; acceptance is invalid.')
    if value.get('launch_pending'):
        lines.append('Ожидается подтверждение запуска процесса; повтор заблокирован.' if ru else 'Unresolved process launch; replay is blocked.')
    if value.get('source_changed_since_start'):
        lines.append('Исходный проект изменился после снимка; изменения не подмешаны.' if ru else 'Origin changed after snapshot; changes were not mixed in.')
    bundle = value.get('report', {}).get('bundle')
    if bundle:
        lines.append(('Пакет: ' if ru else 'Bundle: ') + '.codex-flow/workflows/' + _safe(value['workflow_id'], 32) + '/' + _safe(bundle))
    if value.get('reason'):
        lines.append(('Причина: ' if ru else 'Reason: ') + _safe(value['reason']))
    return '\n'.join(lines)


def setup(value, language='ru'):
    ru = language == 'ru'
    lines = [('Настройка: ' if ru else 'Setup: ') + _safe(value['setup_state']),
             ('Проверки: Python unittest; исходных тестовых файлов ' if ru else 'Checks: Python unittest; baseline test files ') + _safe(value['baseline_test_files'], 8)]
    if value.get('acceptance_file'):
        lines.append(('Контракт: ' if ru else 'Contract: ') + _safe(value['acceptance_file'], 220))
        lines.append(('Шаблон задачи: ' if ru else 'Task template: ') + _safe(value['task_file'], 220))
    lines.append('Модели и проверяющий не запускались.' if ru else 'No models or checker were executed.')
    lines.append('Далее: workflow start "Описание изменения" --dry-run' if ru else 'Next: workflow start "Describe the change" --dry-run')
    return '\n'.join(lines)


def models(value, language='ru'):
    ru = language == 'ru'
    lines = [('Главный профиль: ' if ru else 'Default chief: ') + value['default_chief']]
    for model in value['models']:
        lines.append(_safe(model['id'], 48) + ' | ' + ', '.join(model['roles']) + ' | ' + model['validation_status'])
    lines.append('Доступ текущего аккаунта не проверялся; каталог не меняет маршрутизацию.' if ru else 'Current account access is unknown; catalog does not change routing.')
    return '\n'.join(lines)
