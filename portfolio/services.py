"""Domain operations. Caller owns the connection; mutations own transactions."""
from math import sqrt
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
            db.execute('UPDATE tickets SET status=? WHERE id=?', (status, ticket_id))
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

def experiment_summary(row):
    result = dict(row)
    a = result['a_conversions'] / result['a_visitors']
    b = result['b_conversions'] / result['b_visitors']
    result.update(a_rate=a, b_rate=b, difference=b-a,
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


def ticket_details(db,ticket_id,data):
    assignee,due=assignment(data)
    with db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT assignee,due_date FROM tickets WHERE id=?',(ticket_id,)).fetchone()
        if old is None: raise NotFoundError('Ticket not found')
        if (old['assignee'],old['due_date'])!=(assignee,due):
            db.execute('UPDATE tickets SET assignee=?,due_date=? WHERE id=?',(assignee,due,ticket_id))
            db.execute('INSERT INTO events(ticket_id,detail) VALUES (?,?)',(ticket_id,f"Assignment: {assignee or 'unassigned'}; due: {due or 'none'}"))
    return {'id':ticket_id,'assignee':assignee,'due_date':due}
