package com.example;
import java.nio.file.*;
import java.util.List;
import oshi.SystemInfo;
import oshi.hardware.CentralProcessor;
import oshi.hardware.HardwareAbstractionLayer;
import oshi.software.os.OperatingSystem;
import oshi.software.os.FileSystem;
import oshi.hardware.GlobalMemory;
import oshi.hardware.GraphicsCard;
import com.fasterxml.jackson.databind.ObjectMapper;

public class SystemAssess {
    SystemInfo si = new SystemInfo();
    HardwareAbstractionLayer hal = si.getHardware();
    CentralProcessor cpu = hal.getProcessor();
    OperatingSystem os = si.getOperatingSystem();
    FileSystem fs = os.getFileSystem();
    GlobalMemory memory = hal.getMemory();
    List<GraphicsCard> gp = hal.getGraphicsCards();
    Path path = Paths.get("/Users/apple/Local-Ide/src/main/java/com/example/gpu_tflops.json");
    ObjectMapper mapper = new ObjectMapper();

    double[] tokenpersecond = Suggestion.launch();
    double ONEB = 0;
    double onehalfbillion = 0;
    double halfbillion = 0;
    int size = tokenpersecond.length;
    int validcount = 0;
    private static final double LLAMA_1B_SIZE_GB = 0.60375;
    private static final double QWEN_1_5B_SIZE_GB = 0.905625;
    private static final double QWEN_0_5B_SIZE_GB = 0.301875;
    private static final double OVERHEAD_FACTOR = 1;

    public double bandwidth() {
        ONEB = 0;
        onehalfbillion = 0;
        halfbillion = 0;
        validcount = 0;   

        if (!(tokenpersecond.length < 6)) {
            int index = 0;
            for (double num : tokenpersecond) {
                if (num > 1000 || num == 0) {
                    index++;         
                    continue;
                } else {
                  
                    if (index <= 2) {
                        ONEB += num * LLAMA_1B_SIZE_GB;
                    } else if (index <= 5 && index > 2) {
                        onehalfbillion += num * QWEN_1_5B_SIZE_GB;
                    } else if (index > 5) {
                        halfbillion += num * QWEN_0_5B_SIZE_GB;
                    }
                    validcount++;      
                    index++;          
                }
            }
        }

        if (validcount == 0) return -1;

        double calculatedBandwidth = (ONEB + onehalfbillion + halfbillion) / validcount;

        System.out.println("Raw Token/s Array: " + java.util.Arrays.toString(tokenpersecond));
        System.out.println("Calculated True Bandwidth: " + String.format("%.3f", calculatedBandwidth) + " GB/s");

        return calculatedBandwidth;
    }

    public double estimate(double param, double quantized) {
        double currentBandwidth = bandwidth();
        if (currentBandwidth < 0) return -1;
        double bytesPerParam = quantized / 8.0;
        double modelSizeInGB = param * bytesPerParam * OVERHEAD_FACTOR;
        double tokenestimate = currentBandwidth / modelSizeInGB;
        System.out.println(modelSizeInGB);
        System.out.println("Estimated tokens/sec for " + param + "B Q" + quantized + ": " + String.format("%.2f", tokenestimate));
        return tokenestimate;
    }

    public boolean willitfit(double param, int quantized) {
        double bytesPerParam = quantized / 8.0;
        double modelSizeInGB = param * bytesPerParam * OVERHEAD_FACTOR;

        if (gp == null || gp.isEmpty()) {
            double ramInGB = memory.getTotal() / 1073741824.0;
            return modelSizeInGB <= ramInGB;
        }

        double totalVramInGB = 0;
        for (GraphicsCard card : gp) {
            totalVramInGB += card.getVRam() / 1073741824.0;
        }

        return modelSizeInGB <= totalVramInGB;
    }
    public  OperatingSystem getOperatingSystem() {
        return os;
    }
}