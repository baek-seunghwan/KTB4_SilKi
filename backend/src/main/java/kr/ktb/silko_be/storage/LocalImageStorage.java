package kr.ktb.silko_be.storage;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import kr.ktb.silko_be.common.ApiException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

@Component
@ConditionalOnProperty(name = "app.storage.type", havingValue = "local", matchIfMissing = true)
public class LocalImageStorage implements ImageStorage {
    private final Path root;
    private final String publicBaseUrl;

    public LocalImageStorage(@Value("${app.storage.local-path}") String path,
                             @Value("${app.storage.public-base-url}") String publicBaseUrl) {
        this.root = Path.of(path).toAbsolutePath().normalize();
        this.publicBaseUrl = publicBaseUrl.endsWith("/") ? publicBaseUrl : publicBaseUrl + "/";
        try {
            Files.createDirectories(root);
        } catch (IOException exception) {
            throw new IllegalStateException("로컬 이미지 저장소를 생성할 수 없습니다.", exception);
        }
    }

    @Override
    public StoredImage upload(UUID storeId, MultipartFile file) {
        String key = ImageFiles.key(storeId, ImageFiles.extension(file));
        Path target = root.resolve(key).normalize();
        if (!target.startsWith(root)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_IMAGE", "올바르지 않은 이미지 경로입니다.");
        }
        try {
            Files.createDirectories(target.getParent());
            Files.copy(file.getInputStream(), target, StandardCopyOption.REPLACE_EXISTING);
            return new StoredImage(key, url(key));
        } catch (IOException exception) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "IMAGE_UPLOAD_FAILED", "이미지 저장에 실패했습니다.");
        }
    }

    @Override
    public void delete(String imageKey) {
        if (imageKey == null) return;
        Path target = root.resolve(imageKey).normalize();
        if (!target.startsWith(root)) return;
        try {
            Files.deleteIfExists(target);
        } catch (IOException exception) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "IMAGE_DELETE_FAILED", "이미지 삭제에 실패했습니다.");
        }
    }

    @Override
    public String url(String imageKey) {
        return imageKey == null ? null : publicBaseUrl + imageKey;
    }
}
