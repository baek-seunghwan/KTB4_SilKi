package kr.ktb.silko_be.menu;

public final class DrinkOptions {
    private DrinkOptions() {}

    public enum OptionType { TEMPERATURE, SIZE, EXTRA_SHOT, SWEETNESS }

    public interface Choice {
        OptionType type();
        String displayName();
        long additionalPrice();

        default String code() { return ((Enum<?>) this).name(); }
    }

    public enum Temperature implements Choice {
        HOT("따뜻하게"), ICE("차갑게");

        private final String displayName;

        Temperature(String displayName) { this.displayName = displayName; }
        public OptionType type() { return OptionType.TEMPERATURE; }
        public String displayName() { return displayName; }
        public long additionalPrice() { return 0; }
    }

    public enum DrinkSize implements Choice {
        REGULAR("레귤러", 0), LARGE("라지", 500);

        private final String displayName;
        private final long additionalPrice;

        DrinkSize(String displayName, long additionalPrice) {
            this.displayName = displayName;
            this.additionalPrice = additionalPrice;
        }

        public OptionType type() { return OptionType.SIZE; }
        public String displayName() { return displayName; }
        public long additionalPrice() { return additionalPrice; }
    }

    public enum ExtraShot implements Choice {
        NONE("추가 안 함", 0), SHOT_1("샷 1회 추가", 500), SHOT_2("샷 2회 추가", 1000);

        private final String displayName;
        private final long additionalPrice;

        ExtraShot(String displayName, long additionalPrice) {
            this.displayName = displayName;
            this.additionalPrice = additionalPrice;
        }

        public OptionType type() { return OptionType.EXTRA_SHOT; }
        public String displayName() { return displayName; }
        public long additionalPrice() { return additionalPrice; }
    }

    public enum SweetnessAdjustment implements Choice {
        LESS("덜 달게", -1), NORMAL("보통", 0), MORE("더 달게", 1);

        private final String displayName;
        private final int delta;

        SweetnessAdjustment(String displayName, int delta) {
            this.displayName = displayName;
            this.delta = delta;
        }

        public OptionType type() { return OptionType.SWEETNESS; }
        public String displayName() { return displayName; }
        public long additionalPrice() { return 0; }
        int delta() { return delta; }
    }

    public enum DefaultSweetness {
        LOW, MEDIUM, HIGH;

        public FinalSweetness adjust(SweetnessAdjustment adjustment) {
            return FinalSweetness.values()[ordinal() + 1 + adjustment.delta()];
        }
    }

    public enum FinalSweetness { VERY_LOW, LOW, MEDIUM, HIGH, VERY_HIGH }
}
