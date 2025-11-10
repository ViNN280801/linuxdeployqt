from sys import argv as sys_argv
from sys import exit as sys_exit

from PyQt5.QtWidgets import QApplication

from gui.MainWindow import DependencyDeployerWindow

if __name__ == "__main__":
    try:
        app = QApplication(sys_argv)
        window = DependencyDeployerWindow()
        window.show()
        sys_exit(app.exec_())
    except Exception as e:
        print(e)
        sys_exit(1)
    except KeyboardInterrupt:
        print("User interrupted the program, exiting...")
        sys_exit(1)
