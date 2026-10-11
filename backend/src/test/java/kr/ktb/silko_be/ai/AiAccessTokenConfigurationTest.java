package kr.ktb.silko_be.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.security.KeyPairGenerator;
import java.util.Base64;
import org.junit.jupiter.api.Test;

class AiAccessTokenConfigurationTest {
    @Test
    void readsEscapedNewlinesFromPkcs8EnvironmentValue() throws Exception {
        var generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        var privateKey = generator.generateKeyPair().getPrivate();
        var body = Base64.getMimeEncoder(64, new byte[] {'\n'}).encodeToString(privateKey.getEncoded());
        var pem = "-----BEGIN PRIVATE KEY-----\n" + body + "\n-----END PRIVATE KEY-----";

        var parsed = AiAccessTokenConfiguration.parsePrivateKey(pem.replace("\n", "\\n"));

        assertThat(parsed.getEncoded()).isEqualTo(privateKey.getEncoded());
    }

    @Test
    void rejectsMissingOrNonPkcs8PrivateKey() {
        assertThatThrownBy(() -> AiAccessTokenConfiguration.parsePrivateKey(""))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("required");
        assertThatThrownBy(() -> AiAccessTokenConfiguration.parsePrivateKey(
            "-----BEGIN RSA PRIVATE KEY-----\ninvalid\n-----END RSA PRIVATE KEY-----"))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("PKCS#8");
    }

    @Test
    void rejectsRsaKeyShorterThan2048Bits() throws Exception {
        var generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(1024);
        var privateKey = generator.generateKeyPair().getPrivate();
        var body = Base64.getMimeEncoder(64, new byte[] {'\n'}).encodeToString(privateKey.getEncoded());
        var pem = "-----BEGIN PRIVATE KEY-----\n" + body + "\n-----END PRIVATE KEY-----";

        assertThatThrownBy(() -> AiAccessTokenConfiguration.parsePrivateKey(pem))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("at least 2048 bits");
    }
}
