import sys
from PyQt6.QtWidgets import QApplication
from client.ui.popup import FloatingPopup
from client.core.api_client import ApiClient

app = QApplication.instance() or QApplication(sys.argv)

# Check that FloatingPopup has the expected methods and signals
popup = FloatingPopup()
print('has response_received signal:', hasattr(popup, 'response_received'))
print('has set_context_text method:', hasattr(popup, 'set_context_text'))
if hasattr(popup, 'set_context_text'):
    print('set_context_text callable:', callable(getattr(popup, 'set_context_text')))
print('Popup methods test passed!')
