package kr.ktb.silko_be.storage;

import java.io.IOException;
import java.util.Map;
import kr.ktb.silko_be.common.ApiException;
import org.springframework.http.HttpStatus;
import org.springframework.web.multipart.MultipartFile;

final class ImageFiles {
    private static final long MAX_SIZE = 5L * 1024 * 1024;
    private static final Map<String, String> EXTENSIONS = Map.of(
        "image/jpeg", "jpg",
        "image/png", "png",
        "image/webp", "webp"
    );

    private ImageFiles() {}

    static String extension(MultipartFile file) {
        String extension = EXTENSIONS.get(file.getContentType());
        if (file.isEmpty() || file.getSize() > MAX_SIZE || extension == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_IMAGE",
                "JPEG, PNG, WebP 이미지를 5MB 이하로 업로드해주세요.");
        }
        try {
            byte[] header = file.getInputStream().readNBytes(12);
            if (!matches(extension, header)) throw new IOException();
        } catch (IOException exception) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_IMAGE", "이미지 파일 형식이 올바르지 않습니다.");
        }
        return extension;
    }

    private static boolean matches(String extension, byte[] bytes) {
        return switch (extension) {
            case "jpg" -> bytes.length >= 3
                && (bytes[0] & 0xff) == 0xff && (bytes[1] & 0xff) == 0xd8 && (bytes[2] & 0xff) == 0xff;
            case "png" -> bytes.length >= 8
                && (bytes[0] & 0xff) == 0x89 && bytes[1] == 'P' && bytes[2] == 'N' && bytes[3] == 'G';
            case "webp" -> bytes.length >= 12
                && bytes[0] == 'R' && bytes[1] == 'I' && bytes[2] == 'F' && bytes[3] == 'F'
                && bytes[8] == 'W' && bytes[9] == 'E' && bytes[10] == 'B' && bytes[11] == 'P';
            default -> false;
        };
    }

    static String key(java.util.UUID storeId, String extension) {
        return "stores/" + storeId + "/menus/" + java.util.UUID.randomUUID() + "." + extension;
    }
}
