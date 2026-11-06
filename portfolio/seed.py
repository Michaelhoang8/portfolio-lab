"""Populate an empty workspace with clearly fictional demonstration data."""
import argparse
from .db import initialize, connect
from . import services as s

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='data/portfolio.db')
    args = parser.parse_args()
    initialize(args.database)
    db = connect(args.database)
    try:
        if any(s.snapshot(db).values()):
            parser.exit(1, 'Seed skipped: workspace must be empty. Existing data was preserved.\n')
        for title, description, priority, status in [
            ('Add keyboard navigation','Make the product selector usable without a mouse.','high','active'),
            ('Export workspace data','Download a portable JSON snapshot from the toolbar.','medium','done'),
            ('Document API contracts','Include examples and expected validation errors.','medium','backlog'),
            ('Review empty states','Give new users a clear first action in each app.','low','backlog')]:
            item = s.ticket_create(db, dict(title=title,description=description,priority=priority))['id']
            s.ticket_move(db,item,{'status':status})
        for name,sku,stock,reorder in [('Mechanical keyboard','KEY-101',24,5),('USB-C dock','DOCK-202',3,5),('Studio monitor','MON-303',12,4)]:
            item = s.product_create(db,dict(name=name,sku=sku,reorder_point=reorder))['id']
            s.movement_create(db,dict(product_id=item,delta=stock,note='Fictional opening stock'))
        s.experiment_create(db,dict(name='Demo: checkout button copy',a_visitors=1200,a_conversions=96,b_visitors=1180,b_conversions=118))
        print('Fictional demo data created.')
    finally:
        db.close()

if __name__ == '__main__':
    main()
