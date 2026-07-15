"""자체서명 TLS 인증서 생성 (cryptography, openssl 불필요) — Streamlit HTTPS + 클립보드용.

브라우저의 클립보드 API는 '보안 컨텍스트(HTTPS/localhost)'에서만 동작한다. 사내 LAN(HTTP)에선
막히므로, 서버 IP를 담은 자체서명 인증서로 HTTPS를 켜고 각 개발 PC에 신뢰 설치한다.

사용:  python packaging/gen_cert.py 192.168.155.89 [출력폴더=certs]
생성:  cert.pem, key.pem (서버 Streamlit 용) + cert.crt (개발 PC 신뢰설치용, cert.pem 과 동일)
"""
import datetime
import ipaddress
import os
import sys

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.155.89"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "certs"
    os.makedirs(outdir, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])
    san = [x509.IPAddress(ipaddress.ip_address(ip)),
           x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
           x509.DNSName("localhost")]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))

    with open(os.path.join(outdir, "key.pem"), "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    pem = cert.public_bytes(serialization.Encoding.PEM)
    for fn in ("cert.pem", "cert.crt"):     # cert.crt = 개발 PC 신뢰설치용(동일 내용)
        with open(os.path.join(outdir, fn), "wb") as f:
            f.write(pem)
    print(f"생성 완료: {os.path.abspath(outdir)}  (IP={ip}, 유효 10년)")
    print("  서버:  cert.pem + key.pem  →  start_server.ps1 이 사용")
    print("  개발PC: cert.crt  →  '신뢰할 수 있는 루트 인증 기관'에 설치")


if __name__ == "__main__":
    main()
