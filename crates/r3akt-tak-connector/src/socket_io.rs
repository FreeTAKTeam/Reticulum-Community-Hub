use std::io;
use std::net::{TcpStream, ToSocketAddrs};
use std::time::{Duration, Instant};

/// Bound TCP connection attempts and blocking reads/writes, including TLS I/O.
/// Hostname resolution uses the platform resolver; it is not cancellable here.
pub(super) fn connect_tcp(endpoint: &str, timeout: Duration) -> io::Result<TcpStream> {
    let started = Instant::now();
    let mut last_error = None;
    for address in endpoint.to_socket_addrs()? {
        let remaining = timeout
            .checked_sub(started.elapsed())
            .filter(|remaining| !remaining.is_zero())
            .ok_or_else(|| {
                io::Error::new(io::ErrorKind::TimedOut, "TAK connection deadline exceeded")
            })?;
        match TcpStream::connect_timeout(&address, remaining) {
            Ok(stream) => {
                stream.set_read_timeout(Some(timeout))?;
                stream.set_write_timeout(Some(timeout))?;
                return Ok(stream);
            }
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error.unwrap_or_else(|| {
        io::Error::new(
            io::ErrorKind::AddrNotAvailable,
            "TAK endpoint resolved to no addresses",
        )
    }))
}
