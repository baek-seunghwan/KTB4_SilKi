package kr.ktb.silko_be.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import kr.ktb.silko_be.common.ApiException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

class LocalImageStorageTest {
    @TempDir
    Path directory;

    @Test
    void uploadsAndDeletesImageInsideStoreDirectory() throws Exception {
        var storage = new LocalImageStorage(directory.toString(), "http://localhost/uploads/");
        var storeId = UUID.randomUUID();
        var image = new MockMultipartFile("file", "menu.png", "image/png",
            new byte[] {(byte) 0x89, 'P', 'N', 'G', 13, 10, 26, 10});

        var stored = storage.upload(storeId, image);

        assertThat(stored.imageKey()).startsWith("stores/" + storeId + "/menus/");
        assertThat(Files.exists(directory.resolve(stored.imageKey()))).isTrue();
        assertThat(stored.imageUrl()).isEqualTo("http://localhost/uploads/" + stored.imageKey());

        storage.delete(stored.imageKey());
        assertThat(Files.exists(directory.resolve(stored.imageKey()))).isFalse();
    }

    @Test
    void rejectsContentThatDoesNotMatchImageType() {
        var storage = new LocalImageStorage(directory.toString(), "http://localhost/uploads/");
        var fake = new MockMultipartFile("file", "fake.png", "image/png", "not an image".getBytes());

        assertThatThrownBy(() -> storage.upload(UUID.randomUUID(), fake))
            .isInstanceOf(ApiException.class);
    }
}
