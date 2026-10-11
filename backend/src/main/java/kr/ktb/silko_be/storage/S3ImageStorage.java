package kr.ktb.silko_be.storage;

import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.util.UUID;
import kr.ktb.silko_be.common.ApiException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
@ConditionalOnProperty(name = "app.storage.type", havingValue = "s3")
public class S3ImageStorage implements ImageStorage {
    private final S3Client client;
    private final String bucket;
    private final String publicBaseUrl;

    public S3ImageStorage(@Value("${app.storage.s3-bucket}") String bucket,
                          @Value("${app.storage.s3-region}") String region,
                          @Value("${app.storage.public-base-url}") String publicBaseUrl) {
        if (bucket.isBlank() || publicBaseUrl.isBlank()) {
            throw new IllegalStateException("S3_BUCKET과 IMAGE_PUBLIC_BASE_URL이 필요합니다.");
        }
        this.bucket = bucket;
        this.publicBaseUrl = publicBaseUrl.endsWith("/") ? publicBaseUrl : publicBaseUrl + "/";
        this.client = S3Client.builder().region(Region.of(region)).build();
    }

    @Override
    public StoredImage upload(UUID storeId, MultipartFile file) {
        String key = ImageFiles.key(storeId, ImageFiles.extension(file));
        try {
            client.putObject(PutObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .contentType(file.getContentType())
                    .build(),
                RequestBody.fromInputStream(file.getInputStream(), file.getSize()));
            return new StoredImage(key, url(key));
        } catch (IOException | RuntimeException exception) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "IMAGE_UPLOAD_FAILED", "이미지 저장에 실패했습니다.");
        }
    }

    @Override
    public void delete(String imageKey) {
        if (imageKey == null) return;
        client.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(imageKey).build());
    }

    @Override
    public String url(String imageKey) {
        return imageKey == null ? null : publicBaseUrl + imageKey;
    }

    @PreDestroy
    void close() {
        client.close();
    }
}
