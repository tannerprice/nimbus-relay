APP_NAME=nimbus-relay
APP_USER=nimbus
APP_GROUP=nimbus
INSTALL_DIR=/opt/nimbus-relay
CONFIG_FILE=/opt/nimbus-relay/config.env
SERVICE_FILE=/etc/systemd/system/nimbus-relay.service
PYTHON=python3

.PHONY: help install system-deps user app config icecast service start stop restart status logs uninstall

help:
	@echo "Nimbus Relay setup commands:"
	@echo "  make install      Install everything"
	@echo "  make system-deps  Install apt packages"
	@echo "  make user         Create service user"
	@echo "  make app          Install Python app"
	@echo "  make config       Install config file"
	@echo "  make icecast      Configure Icecast"
	@echo "  make service      Install systemd service"
	@echo "  make start        Start service"
	@echo "  make restart      Restart service"
	@echo "  make logs         Follow logs"
	@echo "  make uninstall    Remove service/app"

install: system-deps user app config icecast service
	@echo "Nimbus Relay installed."
	@echo "Edit $(CONFIG_FILE), then run: sudo make restart"

system-deps:
	sudo apt update
	sudo apt install -y rtl-sdr ffmpeg multimon-ng python3 python3-venv python3-pip git icecast2

user:
	@if ! id "$(APP_USER)" >/dev/null 2>&1; then \
		sudo useradd --system --home "$(INSTALL_DIR)" --shell /usr/sbin/nologin "$(APP_USER)"; \
	fi
	sudo usermod -aG plugdev,audio,dialout "$(APP_USER)"

app:
	sudo mkdir -p "$(INSTALL_DIR)"
	sudo cp -r nimbus_relay pyproject.toml "$(INSTALL_DIR)/"
	sudo chown -R "$(APP_USER):$(APP_GROUP)" "$(INSTALL_DIR)"
	sudo -u "$(APP_USER)" $(PYTHON) -m venv "$(INSTALL_DIR)/.venv"
	sudo -u "$(APP_USER)" "$(INSTALL_DIR)/.venv/bin/pip" install --upgrade pip setuptools wheel
	sudo -u "$(APP_USER)" "$(INSTALL_DIR)/.venv/bin/pip" install -e "$(INSTALL_DIR)"

config:
	@if [ ! -f "$(CONFIG_FILE)" ]; then \
		sudo cp config.env.example "$(CONFIG_FILE)"; \
		sudo chown "$(APP_USER):$(APP_GROUP)" "$(CONFIG_FILE)"; \
		sudo chmod 640 "$(CONFIG_FILE)"; \
		echo "Created $(CONFIG_FILE)"; \
	else \
		echo "$(CONFIG_FILE) already exists; not overwriting."; \
	fi

icecast:
	sudo cp /etc/icecast2/icecast.xml /etc/icecast2/icecast.xml.bak.$$(date +%s) || true
	sudo sh -c 'printf "%s\n" \
	"<icecast>" \
	"  <location>Nimbus Relay</location>" \
	"  <admin>admin@example.com</admin>" \
	"  <limits>" \
	"    <clients>25</clients>" \
	"    <sources>2</sources>" \
	"    <queue-size>524288</queue-size>" \
	"    <client-timeout>30</client-timeout>" \
	"    <header-timeout>15</header-timeout>" \
	"    <source-timeout>10</source-timeout>" \
	"    <burst-on-connect>1</burst-on-connect>" \
	"    <burst-size>65535</burst-size>" \
	"  </limits>" \
	"  <authentication>" \
	"    <source-password>hackme</source-password>" \
	"    <relay-password>hackme</relay-password>" \
	"    <admin-user>admin</admin-user>" \
	"    <admin-password>hackme</admin-password>" \
	"  </authentication>" \
	"  <hostname>localhost</hostname>" \
	"  <listen-socket>" \
	"    <port>8000</port>" \
	"    <bind-address>0.0.0.0</bind-address>" \
	"  </listen-socket>" \
	"  <fileserve>1</fileserve>" \
	"  <paths>" \
	"    <basedir>/usr/share/icecast2</basedir>" \
	"    <logdir>/var/log/icecast2</logdir>" \
	"    <webroot>/usr/share/icecast2/web</webroot>" \
	"    <adminroot>/usr/share/icecast2/admin</adminroot>" \
	"    <alias source=\"/\" destination=\"/status.xsl\"/>" \
	"  </paths>" \
	"  <logging>" \
	"    <accesslog>access.log</accesslog>" \
	"    <errorlog>error.log</errorlog>" \
	"    <loglevel>3</loglevel>" \
	"    <logsize>10000</logsize>" \
	"  </logging>" \
	"  <security>" \
	"    <chroot>0</chroot>" \
	"    <changeowner>" \
	"      <user>icecast2</user>" \
	"      <group>icecast</group>" \
	"    </changeowner>" \
	"  </security>" \
	"</icecast>" \
	> /etc/icecast2/icecast.xml'
	sudo sed -i 's/ENABLE=false/ENABLE=true/g' /etc/default/icecast2 || true
	sudo systemctl enable icecast2
	sudo systemctl restart icecast2

service:
	sudo sh -c 'printf "%s\n" \
	"[Unit]" \
	"Description=Nimbus Relay - RTL-SDR NOAA Weather Radio SAME Relay" \
	"After=network-online.target icecast2.service" \
	"Wants=network-online.target icecast2.service" \
	"" \
	"[Service]" \
	"Type=simple" \
	"User=nimbus" \
	"Group=nimbus" \
	"WorkingDirectory=/opt/nimbus-relay" \
	"Environment=NIMBUS_RELAY_CONFIG=/opt/nimbus-relay/config.env" \
	"ExecStart=/opt/nimbus-relay/.venv/bin/nimbus-relay" \
	"Restart=always" \
	"RestartSec=5" \
	"StandardOutput=journal" \
	"StandardError=journal" \
	"NoNewPrivileges=true" \
	"PrivateTmp=true" \
	"" \
	"[Install]" \
	"WantedBy=multi-user.target" \
	> "$(SERVICE_FILE)"'
	sudo systemctl daemon-reload
	sudo systemctl enable "$(APP_NAME)"

start:
	sudo systemctl start icecast2
	sudo systemctl start "$(APP_NAME)"

stop:
	sudo systemctl stop "$(APP_NAME)"

restart:
	sudo systemctl daemon-reload
	sudo systemctl restart icecast2
	sudo systemctl restart "$(APP_NAME)"

status:
	systemctl status icecast2 --no-pager
	systemctl status "$(APP_NAME)" --no-pager

logs:
	journalctl -u "$(APP_NAME)" -f

icecast-logs:
	journalctl -u icecast2 -f

uninstall:
	sudo systemctl stop "$(APP_NAME)" || true
	sudo systemctl disable "$(APP_NAME)" || true
	sudo rm -f "$(SERVICE_FILE)"
	sudo systemctl daemon-reload
	sudo rm -rf "$(INSTALL_DIR)"
