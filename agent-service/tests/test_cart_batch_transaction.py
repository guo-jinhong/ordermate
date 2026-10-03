import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base, User, Product, CartItem, EcommerceRepository


@pytest.mark.parametrize('failure', ['stock', 'owner', 'stale', 'commit', None])
def test_batch_update_commits_all_or_rolls_back_all(failure):
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([User(id=1, username='owner', password_hash='test'), User(id=2, username='other', password_hash='test')])
        session.add_all([Product(id=8, name='book', category='books', price=99, stock=10),
                         Product(id=9, name='phone', category='electronics', price=100, stock=0 if failure == 'stock' else 10)])
        session.add_all([CartItem(id=71, user_id=1, product_id=8, quantity=3),
                         CartItem(id=72, user_id=2 if failure == 'owner' else 1, product_id=9, quantity=2)])
        session.commit()
        items = [{'cart_id': 71, 'quantity': 1, 'previous_quantity': 3},
                 {'cart_id': 72, 'quantity': 1, 'previous_quantity': 4 if failure == 'stale' else 2}]
        if failure == 'commit':
            def fail_commit(session):
                raise RuntimeError('simulated persistence failure')
            event.listen(session, 'before_commit', fail_commit, once=True)
        repository = EcommerceRepository(session)
        if failure:
            with pytest.raises((ValueError, RuntimeError)):
                repository.update_cart_items(1, items)
        else:
            repository.update_cart_items(1, items)
        session.expire_all()
        quantities = [session.get(CartItem, cid).quantity for cid in [71, 72]]
        assert quantities == ([3, 2] if failure else [1, 1])
    engine.dispose()
