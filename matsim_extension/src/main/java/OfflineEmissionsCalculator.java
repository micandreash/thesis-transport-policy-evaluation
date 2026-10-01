import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.contrib.emissions.EmissionModule;
import org.matsim.contrib.emissions.utils.EmissionsConfigGroup;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.MatsimEventsReader;
import org.matsim.core.events.algorithms.EventWriterXML;
import org.matsim.core.scenario.ScenarioUtils;

import java.io.File;

public class OfflineEmissionsCalculator {

    public static void main(String[] args) {
        System.out.println("Initiating Combined Offline Emission Calculator...");

        // ==========================================
        // 1. SETUP FILE PATHS
        // ==========================================
        String baseDir = "D:/Michael_Thesis/data/final_indicators/";
        String outputDir = baseDir + "emissions_altstadt (some agents need to be filtered)/";
        new File(outputDir).mkdirs();

        String networkFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_munich_1pct_network_connected_hbefa.xml.gz";
        String eventsFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_simulation_output_altstadt/ITERS/it.116/116.events.xml.gz";
        String vehiclesFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_simulation_output_altstadt/output_vehicles.xml.gz";

        String hbefaHotFile = "D:/Michael_Thesis/data/hbefa/EFA_HOT_Vehcat_reformat.csv";
        String hbefaColdFile = "D:/Michael_Thesis/data/hbefa/EFA_ColdStart_Vehcat_michael_thesis_weighted_v4_2.csv";

        // Standard output file for the generated emission events
        String outputEmissionEventsFile = outputDir + "output_emission_events.xml.gz";

        // ==========================================
        // 2. CONFIGURE MATSIM & EMISSIONS MODULE
        // ==========================================
        System.out.println("Configuring MATSim parameters...");
        Config config = ConfigUtils.createConfig();
        config.network().setInputFile(networkFile);
        config.vehicles().setVehiclesFile(vehiclesFile);

        EmissionsConfigGroup emissionsConfig = new EmissionsConfigGroup();

        // Setup HBEFA Factors
        emissionsConfig.setAverageWarmEmissionFactorsFile(hbefaHotFile);
        emissionsConfig.setAverageColdEmissionFactorsFile(hbefaColdFile);
        // Setup Computation Behavior
        emissionsConfig.setEmissionsComputationMethod(EmissionsConfigGroup.EmissionsComputationMethod.AverageSpeed);
        emissionsConfig.setDetailedVsAverageLookupBehavior(EmissionsConfigGroup.DetailedVsAverageLookupBehavior.directlyTryAverageTable);
        emissionsConfig.setHbefaVehicleDescriptionSource(EmissionsConfigGroup.HbefaVehicleDescriptionSource.asEngineInformationAttributes);
        emissionsConfig.setNonScenarioVehicles(EmissionsConfigGroup.NonScenarioVehicles.ignore);

        config.addModule(emissionsConfig);

        // ==========================================
        // 3. LOAD SCENARIO
        // ==========================================
        System.out.println("Loading 3D Network and Vehicles into memory...");
        Scenario scenario = ScenarioUtils.loadScenario(config);

        System.out.println("Validating custom HBEFA attributes on network links...");
        int missingCount = 0;
        for (Link link : scenario.getNetwork().getLinks().values()) {
            if (link.getAttributes().getAttribute("hbefa_road_type") == null) {
                missingCount++;
            }
        }
        if (missingCount > 0) {
            System.out.println("WARNING: " + missingCount + " links are missing the custom HBEFA attribute!");
        }

        // ==========================================
        // 4. PREPARE EVENTS MANAGER & STANDARD WRITER
        // ==========================================
        EventsManager eventsManager = EventsUtils.createEventsManager();

        // Attach standard MATSim XML Event Writer to capture all events
        EventWriterXML eventWriter = new EventWriterXML(outputEmissionEventsFile);
        eventsManager.addHandler(eventWriter);

        // Initialize standard Emission Module (this will inject emission events into the manager)
        new EmissionModule(scenario, eventsManager);

        // ==========================================
        // 5. RUN OFFLINE PLAYBACK
        // ==========================================
        System.out.println("Playing back events to compute emissions...");
        MatsimEventsReader reader = new MatsimEventsReader(eventsManager);
        reader.readFile(eventsFile);

        // Close writer to ensure data is properly compressed and saved
        eventWriter.closeFile();

        System.out.println("Standard Pipeline execution completed successfully.");
        System.out.println("Emission events saved to: " + outputEmissionEventsFile);
    }
}