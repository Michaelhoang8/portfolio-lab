"""Domain operations. Caller owns the connection; mutations own transactions."""
from math import sqrt
from .db import rows
from .validation import ValidationError, NotFoundError, text, integer, choice

def ticket_create(db, data):
    title = text(data, 'title')
    description = text(data, 'description', 4000)
    priority = choice(data, 'priority', ('low', 'medium', 'high'))
    with db:
        ticket_id = db.execute('INSERT INTO tickets(title,description,priority) VALUES (?,?,?)',
                               (title, description, priority)).lastrowid
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
    if delta == 0:
        raise ValidationError('Quantity must not be zero')
    with db:
        # Acquire the write lock before reading stock: concurrent withdrawals cannot oversell.
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT id FROM products WHERE id=?', (product_id,)).fetchone() is None:
            raise NotFoundError('Product not found')
        stock = db.execute('SELECT COALESCE(SUM(delta),0) FROM movements WHERE product_id=?', (product_id,)).fetchone()[0]
        if stock + delta < 0:
            raise ValidationError(f'Insufficient stock: only {stock} available')
        db.execute('INSERT INTO movements(product_id,delta,note) VALUES (?,?,?)', (product_id, delta, note))
    return {'stock': stock + delta}

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
    return {
        'tickets': rows(db.execute('SELECT * FROM tickets ORDER BY id DESC')),
        'events': rows(db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')),
        'products': rows(db.execute('SELECT p.*, COALESCE(SUM(m.delta),0) AS stock FROM products p LEFT JOIN movements m ON p.id=m.product_id GROUP BY p.id ORDER BY p.name')),
        'movements': rows(db.execute('SELECT m.*,p.sku FROM movements m JOIN products p ON m.product_id=p.id ORDER BY m.id DESC LIMIT 100')),
        'experiments': [experiment_summary(row) for row in db.execute('SELECT * FROM experiments ORDER BY id DESC')],
    }
