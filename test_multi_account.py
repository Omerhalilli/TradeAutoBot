import sys
from account_manager import AccountManager, AccountProfile
from handlers import inspect_account_trades, get_accounts_keyboard
from zmq_client import zmq_client

print('=== 1. Testing Account Registry ===')
am = AccountManager()
accounts = am.get_all_accounts()
print(f'Loaded {len(accounts)} accounts:')
assert len(accounts) == 2, f'Expected exactly 2 Invest-AZ accounts, got {len(accounts)}'
for acc in accounts:
    print(f'  Account #{acc.id}: {acc.name} | Number: {acc.account_number} | Server: {acc.server} | Endpoint: {acc.zmq_url}')

print('\n=== 2. Testing Keyboard Generation ===')
kb = get_accounts_keyboard()
assert len(kb.inline_keyboard) == 3, f'Expected 3 keyboard rows, got {len(kb.inline_keyboard)}'
print(f'Keyboard rows: {len(kb.inline_keyboard)} (Demo, Real, Refresh)')

print('\n=== 3. Testing Inspection on Account 1 (Invest-AZ Demo) ===')
am.set_active_account('1')
acc1 = am.get_active_account()
text1, markup1 = inspect_account_trades(acc1)
assert 'ACCOUNT #1: INVEST-AZ DEMO' in text1
assert 'Account Number:' in text1
assert 'BUY / SELL FUNCTION DIAGNOSTICS' in text1
assert 'BUY FUNCTION:' in text1
assert 'SELL FUNCTION:' in text1
print('Demo Inspection Success! Length:', len(text1))

print('\n=== 4. Testing Inspection on Account 2 (Invest-AZ Real) ===')
acc2 = am.get_account_by_id('2')
text2, markup2 = inspect_account_trades(acc2)
assert 'ACCOUNT #2: INVEST-AZ REAL' in text2
assert 'BUY / SELL FUNCTION DIAGNOSTICS' in text2
assert ('DEMO' in text2 or 'REAL' in text2)
print('Real Inspection Success! Length:', len(text2))

print('\n=== 5. Testing Persistence across instance reload ===')
am.set_active_account('1')
am_reloaded = AccountManager()
assert am_reloaded.get_active_account().id == '1', 'Active account failed to persist!'
print('Persistence Verified: Active switched and persisted to ID 1')

# Restore back to Account 2 (Invest-AZ Real)
am.set_active_account('2')
assert am.get_active_account().id == '2'
print('Restored to Account 2 (Invest-AZ Real)')

print('\n[SUCCESS] ALL INVEST-AZ MULTI-ACCOUNT TESTS PASSED!')
