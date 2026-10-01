import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.contrib.noise.NoiseConfigGroup;
import org.matsim.contrib.noise.NoiseOfflineCalculation;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.scenario.ScenarioUtils;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;

public class OfflineNoiseCalculator {

    public static void main(String[] args) {
        System.out.println("Initiating Offline Noise Calculator...");

        // ==========================================
        // 0. SCENARIO SWITCHER
        // 1 = NO Gradient (Z=0), NO Barriers
        // 2 = WITH Gradient, NO Barriers
        // 3 = WITH Gradient, WITH Barriers
        // ==========================================
        int SCENARIO_ID = 3; // Change this value to run different scenarios

        System.out.println("=== RUNNING SCENARIO " + SCENARIO_ID + " ===");

        // ==========================================
        // 1. SETUP FILE PATHS
        // ==========================================
        String baseDir = "D:/Michael_Thesis/data/final_indicators/noise_altstadt_ignore_pt_all_activities/";
        String outputDir = baseDir + "run" + SCENARIO_ID + "/";
        new File(outputDir).mkdirs();

        String networkFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_munich_1pct_network_connected_hbefa.xml.gz";
        String receiversFile = "D:/Michael_Thesis/data/final_indicators/accessibility_munich/null/accessibilities.csv";
        String buildingsFile = "D:/Michael_Thesis/data/bavaria/final_Buildings LoD2 Munich/final_buildings_lod2.geojson";

        // Files from the specific intervened iteration (e.g., it.117)
        String originalEventsFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_simulation_output_altstadt/ITERS/it.116/116.events.xml.gz";
        String populationFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_simulation_output_altstadt/output_plans.xml.gz";
        String vehiclesFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_simulation_output_altstadt/output_vehicles.xml.gz";

        String patchedPopulationFile = outputDir + "patched_plans.xml.gz";

        // ==========================================
        // 2. PATCH POPULATION FILE (ATLANTIS -> EPSG:25832)
        // ==========================================
        File patchedFile = new File(patchedPopulationFile);
        if (patchedFile.exists()) {
            System.out.println("Deleting previously patched population file...");
            patchedFile.delete();
        }

        System.out.println("Brute-forcing CRS patch (ATLANTIS -> EPSG:25832) in population file...");
        try (java.io.BufferedReader reader = new java.io.BufferedReader(new java.io.InputStreamReader(new java.util.zip.GZIPInputStream(new java.io.FileInputStream(populationFile))));
             java.io.BufferedWriter writer = new java.io.BufferedWriter(new java.io.OutputStreamWriter(new java.util.zip.GZIPOutputStream(new java.io.FileOutputStream(patchedPopulationFile))))) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.toLowerCase().contains("atlantis")) {
                    line = line.replaceAll("(?i)ATLANTIS", "EPSG:25832");
                }
                writer.write(line);
                writer.newLine();
            }
            System.out.println("Population file patched successfully!");
        } catch (Exception e) {
            System.out.println("Error patching population file: " + e.getMessage());
        }

        // ==========================================
        // 3. PREPARE EVENTS FILE
        // ==========================================
        String expectedEventsFile = outputDir + "output_events.xml.gz";
        Path linkPath = Paths.get(expectedEventsFile);
        Path targetPath = Paths.get(originalEventsFile);

        try {
            if (Files.exists(linkPath)) {
                Files.delete(linkPath);
            }
            System.out.println("Creating hard link for events file to save disk space and I/O time...");
            Files.createLink(linkPath, targetPath);
        } catch (Exception e) {
            System.out.println("Hard link creation failed, falling back to standard copy operation...");
            try {
                Files.copy(targetPath, linkPath, StandardCopyOption.REPLACE_EXISTING);
            } catch (Exception ex) {
                System.out.println("Warning: Failed to copy events file.");
            }
        }

        // ==========================================
        // 4. CONFIGURE MATSIM & NOISE PARAMETERS
        // ==========================================
        System.out.println("Setting up configurations...");
        Config config = ConfigUtils.createConfig();
        config.controler().setOutputDirectory(outputDir);
        config.global().setCoordinateSystem("EPSG:25832");

        NoiseConfigGroup noiseConfig = new NoiseConfigGroup();

        // 4a. Spatial & Temporal Setup
        noiseConfig.setReceiverPointsCSVFile(receiversFile);
        noiseConfig.setReceiverPointsCSVFileCoordinateSystem("EPSG:25832");
        noiseConfig.setTimeBinSizeNoiseComputation(3600);
        noiseConfig.setScaleFactor(100.0);

        // 4b. Modes & Speed Behaviors
        noiseConfig.setNetworkModesToIgnore("bike,walk,freespeed, pt");
        noiseConfig.setBusIdIdentifiers("bus,tram");
        noiseConfig.setUseActualSpeedLevel(true);
        noiseConfig.setAllowForSpeedsOutsideTheValidRange(false);

        // 4c. Considered Activities
        noiseConfig.setConsideredActivitiesForReceiverPointGrid("home,work,education,leisure,other,shop");
        noiseConfig.setConsideredActivitiesForDamageCalculation("home,work,education,leisure,other,shop");

        // 4d. Noise Computation & Allocation Methodology
        noiseConfig.setNoiseComputationMethod(NoiseConfigGroup.NoiseComputationMethod.RLS19);
        noiseConfig.setNoiseAllocationApproach(NoiseConfigGroup.NoiseAllocationApproach.AverageCost);

        // 4e. Tracking & Internalization Parameters
        noiseConfig.setComputeCausingAgents(true);
        noiseConfig.setComputeNoiseDamages(true);
        noiseConfig.setInternalizeNoiseDamages(false);

        // 4f. Scenario Specifics (Barriers)
        if (SCENARIO_ID == 3) {
            System.out.println("Configuring Noise Barriers (Buildings)...");
            noiseConfig.setConsiderNoiseBarriers(true);
            noiseConfig.setNoiseBarriersSourceCRS("EPSG:25832");
            noiseConfig.setNoiseBarriersFilePath(buildingsFile);
        } else {
            System.out.println("Noise Barriers Disabled.");
            noiseConfig.setConsiderNoiseBarriers(false);
        }

        config.addModule(noiseConfig);

        // ==========================================
        // 5. LOAD SCENARIO & APPLY GRADIENT LOGIC
        // ==========================================
        System.out.println("Loading 3D Network, Vehicles, and Patched Plans...");
        config.network().setInputFile(networkFile);
        config.plans().setInputFile(patchedPopulationFile);
        config.vehicles().setVehiclesFile(vehiclesFile);

        Scenario scenario = ScenarioUtils.loadScenario(config);
        scenario.getConfig().controler().setOutputDirectory(outputDir);

        if (SCENARIO_ID == 1) {
            System.out.println("Removing GRADIENT attributes to disable terrain elevation effects...");
            for (Link link : scenario.getNetwork().getLinks().values()) {
                if (link.getAttributes().getAttribute("GRADIENT") != null) {
                    link.getAttributes().putAttribute("GRADIENT", 0.0);
                }
            }
        }

        // ==========================================
        // 6. EXECUTE OFFLINE CALCULATION
        // ==========================================
        System.out.println("Starting MATSim Offline Noise Calculation...");
        NoiseOfflineCalculation noiseCalculation = new NoiseOfflineCalculation(scenario, outputDir);
        noiseCalculation.run();

        System.out.println("Noise calculation for Scenario " + SCENARIO_ID + " completed successfully! Results are saved in: " + outputDir);
    }
}