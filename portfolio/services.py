"""Domain operations. Caller owns the connection; mutations own transactions."""
from math import sqrt, erfc
import re
from datetime import date
from .db import rows
from .validation import ValidationError, NotFoundError, ConflictError, text, integer, choice

def ticket_create(db, data):
    title = text(data, 'title')
    description = text(data, 'description', 4000)
    priority = choice(data, 'priority', ('low', 'medium', 'high'))
    assignee,due_date = assignment(data)
    with db:
        ticket_id = db.execute('INSERT INTO tickets(title,description,priority,assignee,due_date) VALUES (?,?,?,?,?)',
                               (title, description, priority, assignee, due_date)).lastrowid
        db.execute('INSERT INTO events(ticket_id,detail) VALUES (?,?)', (ticket_id, 'Created in backlog'))
    return {'id': ticket_id}

def ticket_move(db, ticket_id, data):
    status = choice(data, 'status', ('backlog', 'active', 'done'))
    with db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT status FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        if old is None:
            raise NotFoundError('Ticket not found')
        if old['status'] != status:
            db.execute('UPDATE tickets SET status=?,version=version+1 WHERE id=?', (status, ticket_id))
            db.execute('INSERT INTO events(ticket_id,detail) VALUES (?,?)',
                       (ticket_id, f'{old["status"]} → {status}'))
    return {'id': ticket_id, 'status': status}

def product_create(db, data):
    values = (text(data, 'sku', 40).upper(), text(data, 'name'), integer(data, 'reorder_point'))
    with db:
        product_id = db.execute('INSERT INTO products(sku,name,reorder_point) VALUES (?,?,?)', values).lastrowid
    return {'id': product_id}

def movement_create(db, data):
    product_id = integer(data, 'product_id', 1)
    delta = integer(data, 'delta', -1_000_000, 1_000_000)
    note = text(data, 'note', 500)
    request_key = data.get('request_key')
    if request_key is not None and (not isinstance(request_key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', request_key)):
        raise ValidationError('request_key must contain 1–128 ASCII letters, digits, or _ . : -')
    if delta == 0:
        raise ValidationError('Quantity must not be zero')
    with db:
        # Acquire the write lock before reading stock: concurrent withdrawals cannot oversell.
        db.execute('BEGIN IMMEDIATE')
        if request_key is not None:
            previous = db.execute('SELECT * FROM movement_requests WHERE request_key=?', (request_key,)).fetchone()
            if previous:
                if (previous['product_id'], previous['delta'], previous['note']) != (product_id, delta, note):
                    raise ConflictError('request_key was already used for a different movement')
                return {'id': previous['movement_id'], 'stock': previous['stock_after'], 'replayed': True}

        if db.execute('SELECT id FROM products WHERE id=?', (product_id,)).fetchone() is None:
            raise NotFoundError('Product not found')
        stock = db.execute('SELECT COALESCE(SUM(delta),0) FROM movements WHERE product_id=?', (product_id,)).fetchone()[0]
        if stock + delta < 0:
            raise ValidationError(f'Insufficient stock: only {stock} available')
        movement_id = db.execute('INSERT INTO movements(product_id,delta,note) VALUES (?,?,?)', (product_id, delta, note)).lastrowid
        if request_key is not None:
            db.execute('INSERT INTO movement_requests VALUES (?,?,?,?,?,?)',
                       (request_key, movement_id, product_id, delta, note, stock + delta))
    return {'id': movement_id, 'stock': stock + delta, 'replayed': False}

def wilson(successes, total):
    """95% Wilson score interval for a binomial proportion."""
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z*z / total
    center = (p + z*z / (2*total)) / denominator
    radius = z * sqrt(p*(1-p)/total + z*z/(4*total*total)) / denominator
    return [max(0, center-radius), min(1, center+radius)]

def experiment_comparison(a_successes, a_total, b_successes, b_total):
    """Fixed-horizon independent proportions: B minus A, no multiplicity correction."""
    a, b = a_successes / a_total, b_successes / b_total
    # Agresti-Caffo: add one success and one failure to each variant.
    adjusted_a = (a_successes + 1) / (a_total + 2)
    adjusted_b = (b_successes + 1) / (b_total + 2)
    center = adjusted_b - adjusted_a
    radius = 1.959963984540054 * sqrt(adjusted_a * (1-adjusted_a) / (a_total+2)
                                     + adjusted_b * (1-adjusted_b) / (b_total+2))
    pooled = (a_successes + b_successes) / (a_total + b_total)
    expected = [n * p for n in (a_total, b_total) for p in (pooled, 1-pooled)]
    enough = min(expected) >= 5
    z = (b-a) / sqrt(pooled * (1-pooled) * (1/a_total + 1/b_total)) if enough else None
    p_value = erfc(abs(z) / sqrt(2)) if enough else None
    return {'difference_interval':[max(-1,center-radius),min(1,center+radius)],
            'interval_method':'Agresti-Caffo', 'confidence_level':.95,
            'test_method':'Two-sided pooled two-proportion z-test',
            'z_statistic':z, 'p_value':p_value, 'minimum_expected_count':min(expected),
            'alpha':.05, 'status':'insufficient_counts' if not enough else
            ('difference_detected' if p_value < .05 else 'inconclusive')}


def experiment_summary(row):
    result = dict(row)
    a = result['a_conversions'] / result['a_visitors']
    b = result['b_conversions'] / result['b_visitors']
    result.update(comparison=experiment_comparison(result['a_conversions'],result['a_visitors'],
                                                   result['b_conversions'],result['b_visitors']),
                  a_rate=a, b_rate=b, difference=b-a,
                  relative_lift=(b-a)/a if a else None,
                  a_interval=wilson(result['a_conversions'], result['a_visitors']),
                  b_interval=wilson(result['b_conversions'], result['b_visitors']))
    return result

def experiment_create(db, data):
    name = text(data, 'name')
    counts = [integer(data, key, 1 if key.endswith('visitors') else 0)
              for key in ('a_visitors', 'a_conversions', 'b_visitors', 'b_conversions')]
    if counts[1] > counts[0] or counts[3] > counts[2]:
        raise ValidationError('Conversions cannot exceed visitors')
    with db:
        item_id = db.execute('INSERT INTO experiments(name,a_visitors,a_conversions,b_visitors,b_conversions) VALUES (?,?,?,?,?)',
                             (name, *counts)).lastrowid
    return {'id': item_id}

def snapshot(db):
    # One read transaction keeps counts, balances, and ledgers from different
    # concurrent commits out of the same workspace response.
    if db.in_transaction:
        return _snapshot_rows(db)
    with db:
        db.execute('BEGIN')
        return _snapshot_rows(db)


def _snapshot_rows(db):
    return {
        'tickets': rows(db.execute('SELECT * FROM tickets ORDER BY id DESC')),
        'events': rows(db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')),
        'products': rows(db.execute('SELECT p.*, COALESCE(SUM(m.delta),0) AS stock FROM products p LEFT JOIN movements m ON p.id=m.product_id GROUP BY p.id ORDER BY p.name')),
        'movements': rows(db.execute('SELECT m.*,p.sku FROM movements m JOIN products p ON m.product_id=p.id ORDER BY m.id DESC LIMIT 100')),
        'experiments': [experiment_summary(row) for row in db.execute('SELECT * FROM experiments ORDER BY id DESC')],
    }


def assignment(data):
    assignee=data.get('assignee','')
    due=data.get('due_date','')
    if not isinstance(assignee,str) or len(assignee)>120:
        raise ValidationError('Assignee must be text of at most 120 characters')
    if not isinstance(due,str): raise ValidationError('Due date must be YYYY-MM-DD or empty')
    if due:
        try:
            if date.fromisoformat(due).isoformat()!=due: raise ValueError()
        except ValueError:
            raise ValidationError('Due date must be YYYY-MM-DD or empty') from None
    return assignee.strip(),due


def ticket_details(db, ticket_id, data):
    allowed = {'title','description','priority','assignee','due_date','expected_version'}
    if set(data) - allowed:
        raise ValidationError('Unsupported issue detail field')
    if 'expected_version' in data:
        integer(data,'expected_version',1)
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM tickets WHERE id=?',(ticket_id,)).fetchone()
        if row is None:
            raise NotFoundError('Ticket not found')
        old = dict(row)
        merged = {**old, **data}
        assignee, due = assignment(merged)
        values = {'title':text(merged,'title'), 'description':text(merged,'description',4000),
                  'priority':choice(merged,'priority',('low','medium','high')),
                  'assignee':assignee, 'due_date':due}
        changed = [name for name,value in values.items() if old[name] != value]
        if changed:
            if 'expected_version' in data and data['expected_version'] != old['version']:
                raise ConflictError('This issue changed since you opened it. Refresh and review the latest version before saving.')
            db.execute('UPDATE tickets SET title=?,description=?,priority=?,assignee=?,due_date=?,version=version+1 WHERE id=?',
                       (*values.values(),ticket_id))
            db.execute('INSERT INTO events(ticket_id,detail) VALUES (?,?)',
                       (ticket_id,'Updated '+', '.join(name.replace('_',' ') for name in changed)))
        return {'id':ticket_id, **values, 'version':old['version'] + bool(changed)}


def movement_csv(db, batch_size=500):
    """Yield the full ledger as CSV chunks from one SQLite query snapshot."""
    from .data_apps import safe_csv
    cursor = db.execute("""SELECT m.id,m.created_at,p.sku,p.name,m.delta,
        SUM(m.delta) OVER (PARTITION BY m.product_id ORDER BY m.id) AS balance,m.note
        FROM movements m JOIN products p ON p.id=m.product_id ORDER BY m.id""")
    try:
        yield safe_csv(['Movement ID','Timestamp UTC','SKU','Product','Quantity change','Balance after movement','Reason'],[])
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            yield safe_csv([],[[str(value) for value in row] for row in batch],include_header=False)
    finally:
        cursor.close()
