use super::{
    CotUrl, Instant, Read, StdDuration, TakConnectionConfig, TakConnectorError, TakCotReceiver,
    UdpSocket, build_tls_connector, inbound_frames, socket_io,
};
use std::net::TcpStream;

#[derive(Debug)]
enum Stream {
    Tcp(TcpStream),
    Tls(native_tls::TlsStream<TcpStream>),
}

impl Stream {
    fn read(&mut self, bytes: &mut [u8], timeout: StdDuration) -> std::io::Result<usize> {
        match self {
            Self::Tcp(stream) => {
                stream.set_read_timeout(Some(timeout))?;
                stream.read(bytes)
            }
            Self::Tls(stream) => {
                stream.get_ref().set_read_timeout(Some(timeout))?;
                stream.read(bytes)
            }
        }
    }
}

#[derive(Debug)]
pub struct TakSocketReceiver {
    url: CotUrl,
    tls_client_cert: Option<String>,
    tls_client_key: Option<String>,
    tls_ca: Option<String>,
    tls_insecure: bool,
    tls_client_password: Option<String>,
    pytak_tls_dont_verify: u8,
    read_timeout: StdDuration,
    max_bytes: usize,
    stream: Option<Stream>,
    datagram: Option<UdpSocket>,
    buffer: Vec<u8>,
}

// Cloning configuration creates a fresh receiver. A live connection and its
// partial frame always have exactly one owner and cannot be cloned/replayed.
impl Clone for TakSocketReceiver {
    fn clone(&self) -> Self {
        Self {
            url: self.url.clone(),
            tls_client_cert: self.tls_client_cert.clone(),
            tls_client_key: self.tls_client_key.clone(),
            tls_ca: self.tls_ca.clone(),
            tls_insecure: self.tls_insecure,
            tls_client_password: self.tls_client_password.clone(),
            pytak_tls_dont_verify: self.pytak_tls_dont_verify,
            read_timeout: self.read_timeout,
            max_bytes: self.max_bytes,
            stream: None,
            datagram: None,
            buffer: Vec::new(),
        }
    }
}

impl TakSocketReceiver {
    pub fn new(cot_url: &str) -> Result<Self, TakConnectorError> {
        Self::from_config(&TakConnectionConfig {
            cot_url: cot_url.to_string(),
            ..TakConnectionConfig::default()
        })
    }

    pub fn from_config(config: &TakConnectionConfig) -> Result<Self, TakConnectorError> {
        Ok(Self {
            url: CotUrl::parse(&config.cot_url)?,
            tls_client_cert: config.tls_client_cert.clone(),
            tls_client_key: config.tls_client_key.clone(),
            tls_ca: config.tls_ca.clone(),
            tls_insecure: config.tls_insecure,
            tls_client_password: config.tls_client_password.clone(),
            pytak_tls_dont_verify: config.pytak_tls_dont_verify,
            read_timeout: StdDuration::from_secs(2),
            max_bytes: 64 * 1024,
            stream: None,
            datagram: None,
            buffer: Vec::new(),
        })
    }

    #[must_use]
    pub fn with_read_timeout(mut self, timeout: StdDuration) -> Self {
        self.read_timeout = timeout.max(StdDuration::from_millis(1));
        self
    }

    #[must_use]
    pub fn with_max_bytes(mut self, max_bytes: usize) -> Self {
        self.max_bytes = max_bytes.max(1);
        self
    }

    fn connect(&self) -> Result<Stream, TakConnectorError> {
        let stream = socket_io::connect_tcp(&self.url.host_port, self.read_timeout)
            .map_err(|error| TakConnectorError::Receive(error.to_string()))?;
        if self.url.scheme == "tcp" {
            return Ok(Stream::Tcp(stream));
        }
        let connector = build_tls_connector(
            self.tls_ca.as_deref(),
            self.tls_client_cert.as_deref(),
            self.tls_client_key.as_deref(),
            self.tls_client_password.as_deref(),
            self.tls_insecure,
            self.pytak_tls_dont_verify,
        )?;
        connector
            .connect(&self.url.tls_server_name()?, stream)
            .map(Stream::Tls)
            .map_err(|error| TakConnectorError::Receive(format!("TLS handshake: {error:?}")))
    }

    fn receive_stream(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
        if let Some(frame) = inbound_frames::take_frame(&mut self.buffer, self.max_bytes)? {
            return Ok(Some(frame));
        }
        if self.stream.is_none() {
            self.stream = Some(self.connect()?);
        }
        let started = Instant::now();
        let mut chunk = [0_u8; 4096];
        loop {
            let Some(remaining) = self
                .read_timeout
                .checked_sub(started.elapsed())
                .filter(|remaining| !remaining.is_zero())
            else {
                return Ok(None);
            };
            let capacity = self
                .max_bytes
                .saturating_add(1)
                .saturating_sub(self.buffer.len())
                .min(chunk.len());
            let stream = self
                .stream
                .as_mut()
                .ok_or_else(|| TakConnectorError::Receive("CoT stream unavailable".to_string()))?;
            match stream.read(&mut chunk[..capacity], remaining) {
                Ok(0) => {
                    self.stream = None;
                    if self.buffer.iter().all(u8::is_ascii_whitespace) {
                        self.buffer.clear();
                        return Ok(None);
                    }
                    return Err(TakConnectorError::Receive(
                        "CoT connection closed with an incomplete frame".to_string(),
                    ));
                }
                Ok(read) => {
                    self.buffer.extend_from_slice(&chunk[..read]);
                    if let Some(frame) =
                        inbound_frames::take_frame(&mut self.buffer, self.max_bytes)?
                    {
                        return Ok(Some(frame));
                    }
                }
                Err(error)
                    if matches!(
                        error.kind(),
                        std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                    ) =>
                {
                    return Ok(None);
                }
                Err(error) => return Err(TakConnectorError::Receive(error.to_string())),
            }
        }
    }

    fn receive_udp(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
        if self.datagram.is_none() {
            self.datagram = Some(
                UdpSocket::bind(&self.url.host_port)
                    .map_err(|error| TakConnectorError::Receive(error.to_string()))?,
            );
        }
        let socket = self.datagram.as_ref().ok_or_else(|| {
            TakConnectorError::Receive("CoT datagram socket unavailable".to_string())
        })?;
        socket
            .set_read_timeout(Some(self.read_timeout))
            .map_err(|error| TakConnectorError::Receive(error.to_string()))?;
        let mut buffer = vec![0_u8; self.max_bytes.saturating_add(1)];
        match socket.recv(&mut buffer) {
            Ok(read) => {
                buffer.truncate(read);
                let frame = inbound_frames::take_frame(&mut buffer, self.max_bytes)?;
                if frame.is_none() || !buffer.iter().all(u8::is_ascii_whitespace) {
                    return Err(TakConnectorError::Receive(
                        "CoT datagram must contain one complete event".to_string(),
                    ));
                }
                Ok(frame)
            }
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) =>
            {
                Ok(None)
            }
            Err(error) => Err(TakConnectorError::Receive(error.to_string())),
        }
    }
}

impl TakCotReceiver for TakSocketReceiver {
    fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
        let result = match self.url.scheme.as_str() {
            "tcp" | "ssl" | "tls" => self.receive_stream(),
            "udp" => self.receive_udp(),
            other => Err(TakConnectorError::UnsupportedScheme(other.to_string())),
        };
        if result.is_err() {
            self.stream = None;
            self.buffer.clear();
        }
        result
    }
}
