from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDaiEnqIBcN25CP
2VxQp7h/wkLNHs8vzYwiHXDieiOJRVcPcfwJ+3rjwiDPq1vqri5AHYe/NA5+Ea0H
VIXHe2VBRXQrLQ8UHSMIWMA3NwfgTRkMtl1ouG6hE+Ftcz0hyNWwlepmZ39nvjxD
sKd6L5W9Q6Jhgumc+VjRDiJR9YkEdALNTaAepACOkCWN/cfcMRUl8NlCL6sYkh48
HQYCGx3zHp3pHoRN63U5iyzDILgJvVhEj8LByo/yIGlc81mN0mOOmiVHZT8wU3kR
VC/Hs3GDW5RsK4lSoL/afhIjmF84AkeFj7M0omkO7lzGYfcPPcq5EJUN5xpmby6f
LknOL41NAgMBAAECggEADkcRqGjfHyB1dtofrISL8STsny3Guy8CjqDXy3EDBo8j
AgPtEJ9/YIdCN4jQx5A7voqikzzZplj0GHxOntrfO0vhxbrHtziA6nGwYhGHw5rZ
He1OqwhDVuWcOKQ30UMODkYTlQwCbr4m5J4Tdk/9+4PPHyNurSFvyrDR6ZyEjprO
BmMyKGjPOv4a8oZwvgQy31tJFw1YMRimpAm9q6e6nrL1w2yp+/lpwXefutle+Nfq
Q5AzgS3soRNr0/23CsmKAgX2514P151Pj327X0oDQPIZzfok6dgwQcVzR/EgL0GQ
jaG4eSE1Nkx/ieoN562/ZaCoVA4zDTCyliErA50DLQKBgQD4a7ir4whOTSzeflaQ
FiP0jT0QlqXAq95NrCafFelOPM2sOdTpzW6oB394sLbtIT6ubs30GXHQJZWzUJy2
JXpkzT2zVbTlQHgJ2Hrv+nFc7N7l3RqR9cEPV/ABA8THGTKFTHk3nAJy7URIlisx
KPk21Asg93ddGNsRdVq14kEqYwKBgQDhMyAYhhgNhw56W30rw8t5kElh6QjXx8HC
0VkCgMeTX1yfdxvv3WXrPXdn03NVYE36R+yZco9Jidbi/vw2iiMSNmpkWjZS1F6W
NzR1Oh7z05fRDUUMUCsyEqZBA9JLlLdmiE1r8NG1X/Hhxj8I2qFHxirfE89kzjip
5w7a3fmgjwKBgC/jxFQOjllZ815pCJL6UbAhUjZSdF2yREbA+ykL9lAI1LVw6KSx
37UwzNgdaQZJtGW4Iqf+B7zSogtRbQSIMRIhptVdnmPbi8iKHRkKNLRvTYEOoMKm
l7M3hqMLcPHY365m0a9wueAh8Vn06RqvBWwWcJbIXhBqbEDvWK9bkKh1AoGABdWv
RTNkOCWBqIXqTlH6WaH1ZMYG5qBUUtndtoTjptvXqIILhUF1PI0RJO2DlXizTILE
jI09TSh3GtaEbl1R30ztoL/9nFPIR5gSkd75olOfIVl4qoMBO4DkMdcJgc/OmKd7
agqJRGvB9pmOVIpll1h5D+KRgwkcyroj1mPd7d0CgYAQ1qxliKd3oYzhurS6zSrN
TIWcWF9tYDuPf7lSXHSOfRIuvQly3RUu4LStql4Yl3K8kPlMyxndBfCHs+wPOAje
DbzqGZM4TavB9JI/c8jqaTP9ZtkbeR/KPn6jWcw/JvAz8JuYqceSsGF88aa+8LK4
uwEQr3o/j4kU9NrQ0gp+lw==
-----END PRIVATE KEY-----"""

DEFAULT_JWT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2ohJ6iAXDduQj9lcUKe4
f8JCzR7PL82MIh1w4nojiUVXD3H8Cft648Igz6tb6q4uQB2HvzQOfhGtB1SFx3tl
QUV0Ky0PFB0jCFjANzcH4E0ZDLZdaLhuoRPhbXM9IcjVsJXqZmd/Z748Q7Cnei+V
vUOiYYLpnPlY0Q4iUfWJBHQCzU2gHqQAjpAljf3H3DEVJfDZQi+rGJIePB0GAhsd
8x6d6R6ETet1OYsswyC4Cb1YRI/CwcqP8iBpXPNZjdJjjpolR2U/MFN5EVQvx7Nx
g1uUbCuJUqC/2n4SI5hfOAJHhY+zNKJpDu5cxmH3Dz3KuRCVDecaZm8uny5Jzi+N
TQIDAQAB
-----END PUBLIC KEY-----"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "vaultguard"
    mysql_user: str = "vaultguard"
    mysql_password: str = "change_me_mysql_app"
    jwt_issuer: str = "vaultguard"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    mfa_challenge_ttl_minutes: int = 5
    invitation_token_ttl_days: int = 7
    invitation_email_enabled: bool = False
    invitation_link_base_url: str = "http://localhost:5173/invite/accept"
    jwt_private_key_pem: str = DEFAULT_JWT_PRIVATE_KEY
    jwt_public_key_pem: str = DEFAULT_JWT_PUBLIC_KEY

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )

    @property
    def normalized_jwt_private_key(self) -> str:
        return self.jwt_private_key_pem.replace("\\n", "\n")

    @property
    def normalized_jwt_public_key(self) -> str:
        return self.jwt_public_key_pem.replace("\\n", "\n")


settings = Settings()
