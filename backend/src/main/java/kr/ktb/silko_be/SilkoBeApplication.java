package kr.ktb.silko_be;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class SilkoBeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SilkoBeApplication.class, args);
    }

}
