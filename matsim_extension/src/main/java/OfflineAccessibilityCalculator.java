import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.TransportMode;
import org.matsim.contrib.accessibility.AccessibilityConfigGroup;
import org.matsim.contrib.accessibility.AccessibilityModule;
import org.matsim.contrib.accessibility.Modes4Accessibility;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.config.groups.PlanCalcScoreConfigGroup;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.controler.Controler;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.MatsimEventsReader;
import org.matsim.core.router.util.TravelTime;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.trafficmonitoring.TravelTimeCalculator;

import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptorModule;

import java.io.File;

public class OfflineAccessibilityCalculator {

    public static void main(String[] args) {
        System.out.println("Initiating Offline Accessibility Calculator...");

        // ==========================================
        // 1. SETUP FILE PATHS
        // ==========================================
        String baseDir = "D:/Michael_Thesis/data/final_indicators/";
        String outputDir = baseDir + "accessibility_altstadt";
        new File(outputDir).mkdirs();

        String networkFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_munich_1pct_network_connected.xml.gz";
        String facilitiesFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_munich_1pct_facilities.xml.gz";
        String eventsFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_simulation_output_altstadt/ITERS/it.116/116.events.xml.gz";
        String changeEventsFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/interventions/altstadt_change_events_speed_0.xml.gz";

        // Public Transport inputs
        String transitScheduleFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_munich_1pct_transit_schedule.xml.gz";
        String transitVehiclesFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/pop_generation_bavaria/bavaria_1pct_transit_vehicles.xml.gz";

        // Exact boundary shapefile
        String boundaryShapefile = "D:/Michael_Thesis/data/stadtbezirke/final_stadtbezirke_munich.shp";

        // ==========================================
        // 2. CONFIGURE ACCESSIBILITY PARAMETERS
        // ==========================================
        AccessibilityConfigGroup accConfig = new AccessibilityConfigGroup();

        accConfig.setAreaOfAccessibilityComputation(AccessibilityConfigGroup.AreaOfAccesssibilityComputation.fromShapeFile);
        accConfig.setShapeFileCellBasedAccessibility(boundaryShapefile);

        accConfig.setComputingAccessibilityForMode(Modes4Accessibility.freespeed, false);
        accConfig.setComputingAccessibilityForMode(Modes4Accessibility.car, true);
        accConfig.setComputingAccessibilityForMode(Modes4Accessibility.walk, false);
        accConfig.setComputingAccessibilityForMode(Modes4Accessibility.pt, false);
        accConfig.setComputingAccessibilityForMode(Modes4Accessibility.bike, false);

        accConfig.setTileSize_m(50);
        accConfig.setTimeOfDay(8.0 * 3600.0);

        accConfig.setUseParallelization(true);

        // ==========================================
        // 3. CONFIGURE MATSIM SCENARIO
        // ==========================================
        Config config = ConfigUtils.createConfig(accConfig);
        config.plansCalcRoute().setRoutingRandomness(0.0);
        config.plansCalcRoute().setTeleportedModeSpeed(TransportMode.walk, 1.25);
        config.plansCalcRoute().setTeleportedModeSpeed(TransportMode.bike, 3.1);

        config.network().setInputFile(networkFile);
        config.facilities().setInputFile(facilitiesFile);
        config.network().setTimeVariantNetwork(true);
        config.network().setChangeEventsInputFile(changeEventsFile);

        config.transit().setUseTransit(true);
        config.transit().setTransitScheduleFile(transitScheduleFile);
        config.transit().setVehiclesFile(transitVehiclesFile);

        config.controler().setOutputDirectory(outputDir);
        config.controler().setLastIteration(0);
        config.controler().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.deleteDirectoryIfExists);
        config.global().setCoordinateSystem("EPSG:25832");
        config.global().setNumberOfThreads(16);

        // ==========================================
        // 4. INJECT EQASIM SCORING PARAMETERS
        // ==========================================
        PlanCalcScoreConfigGroup scoring = config.planCalcScore();

        // Global Parameters
        scoring.setBrainExpBeta(1.0);
        scoring.setMarginalUtilityOfMoney(0.310998);
        scoring.setPerforming_utils_hr(0.0);

        // Mode: CAR
        PlanCalcScoreConfigGroup.ModeParams carParams = scoring.getOrCreateModeParams("car");
        carParams.setConstant(0.4);
        carParams.setMarginalUtilityOfTraveling(-0.042431 * 60.0);
        carParams.setMarginalUtilityOfDistance(0.0);
        carParams.setMonetaryDistanceRate(-0.2 / 1000.0);

        // Mode: WALK
        PlanCalcScoreConfigGroup.ModeParams walkParams = scoring.getOrCreateModeParams("walk");
        walkParams.setConstant(1.8);
        walkParams.setMarginalUtilityOfTraveling(-0.162285 * 60.0);
        walkParams.setMarginalUtilityOfDistance(0.0);

        // Mode: BIKE
        PlanCalcScoreConfigGroup.ModeParams bikeParams = scoring.getOrCreateModeParams("bike");
        bikeParams.setConstant(-0.5);
        bikeParams.setMarginalUtilityOfTraveling(-0.093485 * 60.0);
        bikeParams.setMarginalUtilityOfDistance(0.0);

        // Mode: PT (Grouped cleanly)
        PlanCalcScoreConfigGroup.ModeParams ptParams = scoring.getOrCreateModeParams("pt");
        ptParams.setConstant(0.0);
        ptParams.setMarginalUtilityOfTraveling(-0.025501 * 60.0);
        scoring.setUtilityOfLineSwitch(-0.417658);
        scoring.setMarginalUtlOfWaitingPt_utils_hr(-0.021801 * 60.0);

        System.out.println("Loading MATSim scenario with Network, Facilities, and Transit...");
        Scenario scenario = ScenarioUtils.loadScenario(config);

        // ==========================================
        // 5. EXTRACT CONGESTED TRAVEL TIMES FROM EVENTS
        // ==========================================
        System.out.println("Parsing events to calculate congested travel times...");

        TravelTimeCalculator.Builder ttBuilder = new TravelTimeCalculator.Builder(scenario.getNetwork());
        TravelTimeCalculator travelTimeCalculator = ttBuilder.build();

        EventsManager eventsManager = EventsUtils.createEventsManager();
        eventsManager.addHandler(travelTimeCalculator);

        MatsimEventsReader eventsReader = new MatsimEventsReader(eventsManager);
        eventsReader.readFile(eventsFile);

        final TravelTime congestedTravelTime = travelTimeCalculator.getLinkTravelTimes();

        // ==========================================
        // 6. EXECUTE ACCESSIBILITY CALCULATION
        // ==========================================
        System.out.println("Starting 0-iteration calculation with congested network state...");
        Controler controler = new Controler(scenario);

        controler.addOverridingModule(new AbstractModule() {
            @Override
            public void install() {
                bind(TravelTime.class).toInstance(congestedTravelTime);
            }
        });

        controler.addOverridingModule(new SwissRailRaptorModule());

        controler.addOverridingModule(new AccessibilityModule());

        controler.run();
        System.out.println("Congested accessibility calculation completed! Results saved in: " + outputDir);
    }
}