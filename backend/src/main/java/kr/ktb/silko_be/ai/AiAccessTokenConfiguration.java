package kr.ktb.silko_be.ai;

import java.security.KeyFactory;
import java.security.NoSuchAlgorithmException;
import java.security.interfaces.RSAPrivateCrtKey;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.RSAPublicKeySpec;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@Configuration(proxyBeanMethods = false)
public class AiAccessTokenConfiguration {
    private static final String PRIVATE_KEY_BEGIN = "-----BEGIN PRIVATE KEY-----";
    private static final String PRIVATE_KEY_END = "-----END PRIVATE KEY-----";

    @Bean
    JwtEncoder aiAccessTokenJwtEncoder(
        @Value("${app.ai.jwt.private-key:}") String configuredPrivateKey
    ) {
        var privateKey = parsePrivateKey(configuredPrivateKey);
        var publicKey = derivePublicKey(privateKey);
        return NimbusJwtEncoder.withKeyPair(publicKey, privateKey).build();
    }

    static RSAPrivateKey parsePrivateKey(String configuredPrivateKey) {
        if (configuredPrivateKey == null || configuredPrivateKey.isBlank()) {
            throw new IllegalStateException("AI JWT PKCS#8 private key is required");
        }

        var pem = configuredPrivateKey.replace("\\n", "\n").trim();
        if (!pem.startsWith(PRIVATE_KEY_BEGIN) || !pem.endsWith(PRIVATE_KEY_END)) {
            throw new IllegalStateException(
                "AI JWT private key must be an RSA PKCS#8 PEM (BEGIN PRIVATE KEY)"
            );
        }

        try {
            var encoded = pem.substring(PRIVATE_KEY_BEGIN.length(), pem.length() - PRIVATE_KEY_END.length())
                .replaceAll("\\s", "");
            var keySpec = new PKCS8EncodedKeySpec(Base64.getDecoder().decode(encoded));
            var privateKey = KeyFactory.getInstance("RSA").generatePrivate(keySpec);
            if (!(privateKey instanceof RSAPrivateKey rsaPrivateKey)) {
                throw new IllegalStateException("AI JWT private key must use RSA");
            }
            if (rsaPrivateKey.getModulus().bitLength() < 2048) {
                throw new IllegalStateException("AI JWT RSA private key must be at least 2048 bits");
            }
            return rsaPrivateKey;
        } catch (IllegalArgumentException | InvalidKeySpecException | NoSuchAlgorithmException exception) {
            throw new IllegalStateException("AI JWT private key is not a valid RSA PKCS#8 PEM", exception);
        }
    }

    private static RSAPublicKey derivePublicKey(RSAPrivateKey privateKey) {
        if (!(privateKey instanceof RSAPrivateCrtKey crtKey)) {
            throw new IllegalStateException(
                "AI JWT private key must include the RSA public exponent (PKCS#8 CRT key)"
            );
        }
        try {
            var keySpec = new RSAPublicKeySpec(crtKey.getModulus(), crtKey.getPublicExponent());
            return (RSAPublicKey) KeyFactory.getInstance("RSA").generatePublic(keySpec);
        } catch (InvalidKeySpecException | NoSuchAlgorithmException exception) {
            throw new IllegalStateException("Unable to derive the AI JWT public key", exception);
        }
    }
}
