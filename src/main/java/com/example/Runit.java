package com.example;
import java.util.Map;
import java.io.IOException;
import java.net.ServerSocket;
import java.lang.ProcessBuilder;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.HashMap;
import java.util.List;
import java.util.concurrent.CountDownLatch; 
import java.util.concurrent.TimeUnit;    
import java.io.File;
import java.nio.file.Paths;
class Suggestion {
    public static double EasyParser(String jsonResponse) {
        try {
            ObjectMapper mapper = new ObjectMapper();
            JsonNode root = mapper.readTree(jsonResponse);
            double tokensPerSecond = root.path("timings").path("predicted_per_second").asDouble();
            return tokensPerSecond;
        } catch (Exception e) {
            System.err.println("Failed to parse JSON: " + e.getMessage());
            return 0.0;
        }
    }

    public static int searchport() {
        try (ServerSocket socket = new ServerSocket(0)) {
            int freePort = socket.getLocalPort();
            System.out.println("Found a free port: " + freePort);
            return freePort;
        } catch (IOException e) {
            System.err.println("Could not find a free port: " + e.getMessage());
        }
        return -1;
    }

public static double[] launch() {
    String[] modelPath = new String[3];
    String[] prompts = new String[3];
    prompts[0] = "Hi who are you ?";
    prompts[1] = "Write a 300 huge essay on local llms";
    prompts[2] = "Calculate the radius of an sphere exerting a gravitional force of 1000N to an object at a distance of 0.5m away from it? ";
    modelPath[0] = "src/main/java/com/example/LLMs/Llama-3.2-1B-Instruct-Q4_K_M.gguf";
    modelPath[1] = "src/main/java/com/example/LLMs/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf";
    modelPath[2]="src/main/java/com/example/LLMs/qwen2.5-0.5b-instruct-q4_k_m.gguf";
    double[] Token_persecond = new double[9];
    int tokenmapping=0;
    HttpClient client = HttpClient.newHttpClient();
    String osName = System.getProperty("os.name").toLowerCase();
    String baseName= "llamafile-0.10.4-thin";
    if (osName.contains("win")) {
        baseName +=".exe";
    }
    File execFile = Paths.get("src", "main", "java", "com", "example", "resources","Llamafile", baseName).toFile();
    if (!osName.contains("win")) {
        if (!execFile.setExecutable(true)) {
            System.err.println("Failed to set executable permission for " + execFile.getAbsolutePath());
        }
    }
    System.out.println("[DEBUG] Executable path: " + execFile.getAbsolutePath());
System.out.println("[DEBUG] Exists: " + execFile.exists());
System.out.println("[DEBUG] Can execute: " + execFile.canExecute());
    for (int i = 0; i <= 2; i++) {
        int freePort = searchport();
        if (freePort == -1) continue;
        int promptIndex = 0; 
        Process serverProcess = null;
        Thread shutdownHook = null;
        
        try {
            System.out.println("\n[Launcher] Starting Model " + (i + 1) + " on port " + freePort);
            
            ProcessBuilder pb = new ProcessBuilder(
    execFile.getAbsolutePath(),
    "-m", modelPath[i],
    "-ngl","999",
    "-c", "2048",
    "--port", String.valueOf(freePort),
    "--server"   
);
            pb.redirectErrorStream(true);
            serverProcess = pb.start();
            final Process activeProcess = serverProcess;
            
            shutdownHook = new Thread(() -> {
                System.out.println("\n[Emergency] Killing active server process...");
                activeProcess.destroyForcibly();
            });
            Runtime.getRuntime().addShutdownHook(shutdownHook);
            
            CountDownLatch serverReadyLatch = new CountDownLatch(1);
            
            Thread logThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(activeProcess.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        System.out.println("[llama-server-" + (activeProcess.hashCode() % 100) + "] " + line);
                        if (line.contains("listening on http://")) {
                            System.out.println("[Launcher] Server is ready!");
                            serverReadyLatch.countDown();
                        }
                    }
                } catch (IOException e) {
                    System.err.println("[Log] Failed to read server output: " + e.getMessage());
                }
            });
            logThread.setDaemon(true);
            logThread.start();
            
            System.out.println("[Launcher] Waiting for server to be ready...");
            boolean serverReady = serverReadyLatch.await(30, TimeUnit.SECONDS);
            
            if (!serverReady) {
                System.err.println("[Launcher] Server didn't become ready within 30 seconds!");
                continue;
            }
            
            System.out.println("[Launcher] Server ready! Sending prompt: " + prompts[i]);
            for(int j=0;j<3;j++){

            Map<String, Object> payload = new HashMap<>();
            payload.put("model", "qwen2.5-coder");
            payload.put("prompt", prompts[promptIndex]);
            payload.put("temperature", 0.7);
            payload.put("max_tokens", 512);
            payload.put("stream", false);
            payload.put("stop", List.of("<|fim_prefix|>", "<|fim_suffix|>", "<|fim_middle|>", "<|fim_pad|>", "\n\n"));
            String json = new ObjectMapper().writeValueAsString(payload);
            
      
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("http://localhost:" + freePort + "/v1/completions"))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(60))
                    .POST(HttpRequest.BodyPublishers.ofString(json))
                    .build();
            
            System.out.println("[Launcher] Sending request for model " + (i + 1) + "...");
            
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (EasyParser(response.body())<1000){
            Token_persecond[tokenmapping]=EasyParser(response.body());
            promptIndex+=1;
            tokenmapping+=1;}
            System.out.println("[API Response] Status: " + response.statusCode());
            if (response.statusCode() == 200) {
                try {
                    ObjectMapper mapper = new ObjectMapper();
                    JsonNode root = mapper.readTree(response.body());
                    JsonNode choices = root.path("choices");
                    if (choices.isArray() && choices.size() > 0) {
                        String text = choices.get(0).path("text").asText();
                        System.out.println("[API Response] Content: " + text);
                        
                        JsonNode timings = root.path("timings");
                        double tokensPerSecond = timings.path("predicted_per_second").asDouble();
                        System.out.println("[API Response] Speed: " + String.format("%.2f", tokensPerSecond) + " tokens/sec");
                    }
                } catch (Exception e) {
                    System.out.println("[API Response] Raw: " + response.body());
                }
            } else {
                System.out.println("[API Response] Error Body: " + response.body());
            }}
            
            System.out.println("[Launcher] Completed request for model " + (i + 1));
            
            
        } catch (Exception e) {
            System.err.println("[Launcher] Failed for model " + (i + 1) + ": " + e.getMessage());
            e.printStackTrace();
        } finally {
            if (serverProcess != null) {
                System.out.println("[Launcher] Shutting down server for model " + (i + 1));
                serverProcess.destroy();
                try {
                    serverProcess.waitFor(5, TimeUnit.SECONDS);
                } catch (InterruptedException e) {
                    serverProcess.destroyForcibly();
                }
            }
            if (shutdownHook != null) {
                try {
                    Runtime.getRuntime().removeShutdownHook(shutdownHook);
                } catch (IllegalStateException e) {
                }
            }
        }
        
        System.out.println("[Launcher] === Completed model " + (i + 1) + " ===");
    }
    System.out.println("\n[Queue] All models have executed and closed back-to-back successfully.");

return Token_persecond;
    
}
}
public class Runit {
    public static void main(String[] args) {
        Suggestion.launch();
    }
}
