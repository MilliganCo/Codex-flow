"""Small JSON CLI used only by the sandboxed acceptance example."""
import json
import sys


def main():
    try:
        data = json.loads(sys.stdin.read())
        if (not isinstance(data, dict) or set(data) != {'numbers'} or not isinstance(data['numbers'], list)
                or any(type(n) is not int for n in data['numbers'])):
            raise ValueError('integer list required')
        print(json.dumps({'sum': sum(data['numbers'])}))
        return 0
    except (ValueError, TypeError):
        print('invalid input', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
