package kr.ktb.silko_be.storage;

import java.util.UUID;
import org.springframework.web.multipart.MultipartFile;

public interface ImageStorage {
    StoredImage upload(UUID storeId, MultipartFile file);
    void delete(String imageKey);
    String url(String imageKey);
}
