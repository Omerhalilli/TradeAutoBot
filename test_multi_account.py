import sys
from account_manager import AccountManager, AccountProfile
from handlers import inspect_account_trades, get_accounts_keyboard
from zmq_client import zmq_client

print('=== 1. Testing Account Registry ===')
am = AccountManager()
accounts = am.get_all_accounts()
assert len(accounts) >= 3, f'Expected at least 3 accounts, got {len(accounts)}'
for acc in accounts:
    print(f'Account #{acc.id}: {acc.name} | Number: {acc.account_number} | Profile: {acc.profile_name} | Endpoint: {acc.zmq_url}')

print('\n=== 2. Testing Keyboard Generation ===')
kb = get_accounts_keyboard()
assert len(kb.inline_keyboard) >= 4
print('Keyboard rows:', len(kb.inline_keyboard))

print('\n=== 3. Testing Inspection on Account 1 (Live) ===')
am.set_active_account('1')
acc1 = am.get_active_account()
text1, markup1 = inspect_account_trades(acc1)
assert 'ACCOUNT #1' in text1
assert 'BUY / SELL FUNCTION DIAGNOSTICS' in text1
print('Live Inspection Success! Length:', len(text1))

print('\n=== 4. Testing Inspection on Account 2 (Offline Simulation) ===')
acc2 = am.get_account_by_id('2')
text2, markup2 = inspect_account_trades(acc2)
assert 'OFFLINE / UNREACHABLE' in text2
print('Offline Inspection Handled Gracefully!')

print('\n=== 5. Testing Persistence across instance reload ===')
am.set_active_account('2')
am_reloaded = AccountManager()
assert am_reloaded.get_active_account().id == '2', 'Active account failed to persist!'
print('Persistence Verified: Active is ID 2')

# Restore back to Account 1
am.set_active_account('1')
assert am.get_active_account().id == '1'
print('Restored to Account 1')

print('\n[SUCCESS] ALL MULTI-ACCOUNT UNIT TESTS PASSED!')
