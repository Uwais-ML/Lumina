package com.example;
import java.io.File;
import java.util.List;
public class showmodel {
   static List<String> llminfo = new java.util.ArrayList<>();
    public void ascparam(List<String> llminfo){
        showmodel.llminfo = llminfo;
        
    }
    public static void main(String[] args) {
            String firstdirectory = "src/main/java/com/example/LLMs/";
            int i = 0;
        try {
            File directory = new File(firstdirectory);
            for (File file : directory.listFiles()) {
                if (file.getName().endsWith(".gguf")) {
                    System.out.println(i+1 +". " + file.getName() + "\n");
                    showmodel.llminfo.add(file.getName());
                    i++;
                }
            }
        } catch (Exception e) {
            System.out.println("Error: " + e.getMessage());
        }
    }
}