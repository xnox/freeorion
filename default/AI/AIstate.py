import copy
import freeOrionAIInterface as fo
import EnumsAI
from EnumsAI import AIFleetMissionType, AIShipRoleType, AIExplorableSystemType,  AITargetType
import AIFleetMission
import FleetUtilsAI
import ExplorationAI
from MilitaryAI import MinThreat

##moving ALL or NEARLY ALL  'global' variables into AIState object rather than module
# global variables
foodStockpileSize = 1     # food stored per population
minimalColoniseValue = 3  # minimal value for a planet to be colonised
colonisablePlanetIDs = []  # TODO: move into AIstate
colonyTargetedSystemIDs = []
colonisableOutpostIDs = []  # TODO: move into AIstate
outpostTargetedSystemIDs = []
opponentPlanetIDs = []
invasionTargetedSystemIDs = []
militarySystemIDs = []
militaryTargetedSystemIDs = []
colonyFleetIDs = []
outpostFleetIDs = []
invasionFleetIDs = []
militaryFleetIDs = []
fleetsLostBySystem={}
fleetsLostByID={}

def dictFromMap(map):
    return dict(  [  (el.key(),  el.data() ) for el in map ] )

# AIstate class
class AIstate(object):
    "stores AI game state"

    # def colonisablePlanets (should be set at start of turn)
    # getColonisablePlanets (deepcopy!)

    def __init__(self):
        "constructor"
        # 'global' (?) variables
        self.foodStockpileSize =  1    # food stored per population
        self.minimalColoniseValue = 3  # minimal value for a planet to be colonised
        self.colonisablePlanetIDs = []  # TODO: move into AIstate
        self.colonyTargetedSystemIDs = []
        self.colonisableOutpostIDs = []  # TODO: move into AIstate
        self.outpostTargetedSystemIDs = []
        self.opponentPlanetIDs = []
        self.invasionTargetedSystemIDs = []
        self.militarySystemIDs = []
        self.militaryTargetedSystemIDs = []
        self.colonyFleetIDs = []
        self.outpostFleetIDs = []
        self.invasionFleetIDs = []
        self.militaryFleetIDs = []
        
        self.untaskedFleets=[]
        self.__missionsByType = {}
        for missionType in EnumsAI.getAIFleetMissionTypes():
            self.__missionsByType[missionType] = {}

        self.__aiMissionsByFleetID = {}

        self.__shipRoleByDesignID = {}
        self.__fleetRoleByID = {}
        self.__designStats={}
        self.__priorityByType = {}

        #self.__explorableSystemByType = {}
        #for explorableSystemsType in EnumsAI.getAIExplorableSystemTypes():
        #    self.__explorableSystemByType[explorableSystemsType] = {}
            
        #initialize home system knowledge
        universe = fo.getUniverse()
        empire = fo.getEmpire()
        self.empireID = empire.empireID
        self.origHomeworldID = empire.capitalID
        homeworld = universe.getPlanet(self.origHomeworldID)
        self.origSpeciesName = homeworld.speciesName
        self.origHomeSystemID = homeworld.systemID
        self.visBorderSystemIDs = {self.origHomeSystemID:1}
        self.visInteriorSystemIDs= {}
        self.expBorderSystemIDs = {self.origHomeSystemID:1}
        self.expInteriorSystemIDs= {}
        self.exploredSystemIDs = {}
        self.unexploredSystemIDs = {self.origHomeSystemID:1}
        self.fleetStatus={}
        self.systemStatus={}

    def __del__(self):
        "destructor"
        del self.__missionsByType
        del self.__shipRoleByDesignID
        del self.__fleetRoleByID
        del self.__priorityByType
        #del self.__explorableSystemByType
        del self.__aiMissionsByFleetID
        del self.colonisablePlanetIDs
        del self.colonyTargetedSystemIDs
        del self.colonisableOutpostIDs
        del self.outpostTargetedSystemIDs
        del self.opponentPlanetIDs
        del self.invasionTargetedSystemIDs
        del self.militarySystemIDs
        del self.militaryTargetedSystemIDs
        del self.colonyFleetIDs 
        del self.outpostFleetIDs 
        del self.invasionFleetIDs 
        del self.militaryFleetIDs 
        
    def clean(self):
        "turn start AIstate cleanup"
        
        fleetsLostBySystem.clear()
        fleetsLostByID.clear()
        
        ExplorationAI.graphFlags.clear()
        print "-------------------------------------------------"
        print "Border Exploration Update"
        print "-------------------------------------------------"
        for sysID in list(self.visBorderSystemIDs):
            ExplorationAI.followVisSystemConnections(sysID,  self.origHomeSystemID)
        newlyExplored = ExplorationAI.updateExploredSystems()
        nametags=[]
        universe = fo.getUniverse()
        for sysID in newlyExplored:
            newsys = universe.getSystem(sysID)
            nametags.append(  "ID:%4d -- %20s"%(sysID, (newsys and newsys.name) or"name unknown"  )    )# an explored system *should* always be able to be gotten 
        if newlyExplored:
            print "-------------------------------------------------"
            print "newly explored systems: \n"+"\n".join(nametags)
            print "-------------------------------------------------"
        # cleanup fleet roles
        #self.updateFleetLocs()
        self.__cleanFleetRoles()
        self.__cleanAIFleetMissions(FleetUtilsAI.getEmpireFleetIDs())
        print "Fleets lost by system: %s"%fleetsLostBySystem
        self.updateSystemThreats()
        ExplorationAI.updateScoutFleets() #should do this after clearing dead  fleets, currently should be already done here

    def updateFleetLocs(self):
        universe=fo.getUniverse()
        movedFleets=[]
        for fleetID in self.fleetStatus:
            oldLoc=self.fleetStatus[fleetID]['sysID']
            fleet = universe.getFleet(fleetID)
            if not fleet:
                print "can't retrieve fleet %4d to update loc"%fleetID
            newLoc = fleet.systemID
            if newLoc != oldLoc:
                movedFleets.append( (fleetID,  oldLoc,  newLoc) )
                self.fleetStatus[fleetID]['sysID']= newLoc
        if movedFleets:
            print "(moved_fleet,  oldSys,  newSys): %s"%movedFleets
        else:
            print "no moved_fleets this turn"

    def deleteFleetInfo(self,  fleetID):
        if fleetID in self.__aiMissionsByFleetID:
            del self.__aiMissionsByFleetID[fleetID]
        if fleetID in self.fleetStatus:
            del self.fleetStatus[fleetID]
        if fleetID in self.__fleetRoleByID:
            del self.__fleetRoleByID[fleetID]

    def reportSystemThreats(self, sysIDList=None):
        universe = fo.getUniverse()
        if sysIDList is None:
            sysIDList = sorted( universe.systemIDs )# will normally look at this, the list of all known systems
        #assess fleet and planet threats
        print "----------------------------------------------"
        print "System Threat Assessments"
        for sysID in sysIDList:
            sysStatus = self.systemStatus.get(sysID,  {})
            system = universe.getSystem(sysID)
            print "System %4d  ( %12s ) : %s"%(sysID,  (system and system.name) or "unkown",  sysStatus)

    def updateSystemThreats(self,  sysIDList=None):
        universe = fo.getUniverse()
        if sysIDList is None:
            sysIDList = universe.systemIDs # will normally look at this, the list of all known systems
        #assess fleet and planet threats
        for sysID in sysIDList:
            sysStatus = self.systemStatus.get(sysID,  {})
            system = universe.getSystem(sysID)
            if (not system) or not (universe.getVisibility(sysID,  self.empireID) >= fo.visibility.partial):
                sysStatus['fleetThreat'] = int( max( sysStatus.get('fleetThreat',  0) ,  1.2*sum(fleetsLostBySystem.get(sysID,  []) ))   ) # if no current info, leave as previous, or 0 if no previous rating ,  or rating of fleets lost
                sysStatus['planetThreat'] = int( sysStatus.get('planetThreat',  0) ) # if no current info, leave as previous, or 0 if no previous rating
                self.systemStatus[sysID] = sysStatus
                continue
            else:
                threat=0
                for fleetID in system.fleetIDs:
                    fleet = universe.getFleet(fleetID)
                    if ( fleet) and  (not fleet.ownedBy(self.empireID)):
                        threat += self.rateFleet(fleetID)#currently treating all unowned fleets as hostile
                sysStatus['fleetThreat'] = int( threat ) #TODO: revisit this treatment
                sysStatus['fleetThreat'] = int( max( sysStatus.get('fleetThreat',  0) ,  sum(fleetsLostBySystem.get(sysID,  []) ))  )#apparently logged as visisble for rest of turn even if can no longer get sys contents
                threat=0
                for planetID in system.planetIDs:
                    planet = universe.getPlanet(planetID)
                    if planet and ( not planet.unowned ) and (not planet.ownedBy(self.empireID)) :
                        try:
                            threat += ( planet.currentMeterValue(fo.meterType.defense) ) * ( planet.currentMeterValue(fo.meterType.shield) +1)
                        except:
                            print "Error:  couldn't read meters for threat assessment of visible planet %d : %s"%(planetID,  planet.name)
                            pass
                sysStatus['planetThreat'] = int( threat )
                self.systemStatus[sysID] = sysStatus

        #assess secondary threats (one half of threats of surrounding systems
        for sysID in sysIDList:
            sysStatus = self.systemStatus[sysID]
            system = universe.getSystem(sysID)
            if (not system) :
                sysStatus['neighborThreat'] = sysStatus.get('neighborThreat',  0) # if no current info, leave as previous, or 0 if no previous rating
                self.systemStatus[sysID] = sysStatus
                continue
            else:
                threat=0
                neighbors = dictFromMap( universe.getSystemNeighborsMap(sysID,  self.empireID) ).keys()
                for neighborID in neighbors:
                    threat += 0.5* self.systemStatus.get(neighborID,  {}).get('fleetThreat',  0)
                sysStatus['neighborThreat'] = int( threat + 0.5 )
                self.systemStatus[sysID] = sysStatus

    def afterTurnCleanup(self):
        "removes not required information to save from AI state after AI complete its turn"
        # some ships in fleet can be destroyed between turns and then fleet may have have different roles
        #self.__fleetRoleByID = {}
        pass

    def __hasAIFleetMission(self, fleetID):
        "returns True if fleetID has AIFleetMission"
        return self.__aiMissionsByFleetID.__contains__(fleetID)

    def getAIFleetMission(self, fleetID):
        "returns AIFleetMission with fleetID"
        if fleetID in self.__aiMissionsByFleetID:
            return self.__aiMissionsByFleetID[fleetID]
        else:
            return None

    def getAllAIFleetMissions(self):
        "returns all AIFleetMissions"

        return self.__aiMissionsByFleetID.values()

    def getFleetMissionsMap(self):
        return self.__aiMissionsByFleetID

    def getAIFleetMissionsWithAnyMissionTypes(self, fleetMissionTypes):
        "returns all AIFleetMissions which contains any of fleetMissionTypes"

        result = []

        aiFleetMissions = self.getAllAIFleetMissions()
        for aiFleetMission in aiFleetMissions:
            if aiFleetMission.hasAnyOfAIMissionTypes(fleetMissionTypes):
                result.append(aiFleetMission)
        return result

    def __addAIFleetMission(self, fleetID):
        "add new AIFleetMission with fleetID if it already not exists"

        if self.getAIFleetMission(fleetID) == None:
            aiFleetMission = AIFleetMission.AIFleetMission(fleetID)
            self.__aiMissionsByFleetID[fleetID] = aiFleetMission

    def __removeAIFleetMission(self, fleetID):
        "remove invalid AIFleetMission with fleetID if it exists"

        aiFleetMission = self.getAIFleetMission(fleetID)
        if aiFleetMission != None:
            self.__aiMissionsByFleetID[fleetID] = None
            del aiFleetMission
            del self.__aiMissionsByFleetID[fleetID]

    def __cleanAIFleetMissions(self, fleetIDs):
        "cleanup of AIFleetMissions"

        for fleetID in fleetIDs:
            if self.getAIFleetMission(fleetID) == None:
                self.__addAIFleetMission(fleetID)

        aiFleetMissions = self.getAllAIFleetMissions()
        deletedFleetIDs = []
        for aiFleetMission in aiFleetMissions:
            if not(aiFleetMission.getAITargetID() in fleetIDs):
                deletedFleetIDs.append(aiFleetMission.getAITargetID())
        for deletedFleetID in deletedFleetIDs:
            self.__removeAIFleetMission(deletedFleetID)

        aiFleetMissions = self.getAllAIFleetMissions()
        for aiFleetMission in aiFleetMissions:
            aiFleetMission.cleanInvalidAITargets()

    def hasAITarget(self, aiFleetMissionType, aiTarget):
        aiFleetMissions = self.getAIFleetMissionsWithAnyMissionTypes([aiFleetMissionType])
        for mission in aiFleetMissions:
            if mission.hasTarget(aiFleetMissionType, aiTarget):
                return True
        return False

        aiFleetMissions = self.getAIFleetMissionsWithAnyMissionTypes([aiFleetMissionType])
        for mission in aiFleetMissions:
            if mission.hasTarget(aiFleetMissionType, aiTarget):
                return True
        return False

    def rateFleet(self, fleetID):
        universe=fo.getUniverse()
        fleet=universe.getFleet(fleetID)
        if fleet and (not fleet.aggressive) and fleet.ownedBy(self.empireID):
            pass
            #fleet.setAggressive(True)
        if not fleet:
            return 0
        rating=0
        for shipID in fleet.shipIDs:
            #could approximate by design, but checking  meters has better current accuracy
            ship = universe.getShip(shipID)
            if not ship: 
                continue
            stats = self.getDesignIDStats(ship.designID)
            rating += stats['attack'] * ( stats['structure'] + stats['shields'] )
        return rating

    def getRating(self,  fleetID):
        if fleetID in self.fleetStatus:
            return self.fleetStatus[fleetID].get('rating', 0)
        else:
            fleet = fo.getUniverse().getFleet(fleetID)
            if not fleet: return 0
            status = {'rating':self.rateFleet(fleetID),  'sysID':fleet.systemID}
            self.fleetStatus[fleetID] = status
            return status['rating']

    def updateFleetRating(self, fleetID):
        universe = fo.getUniverse()
        fleet = universe.getFleet(fleetID)
        if not fleet:
            return None
        newRating = self.rateFleet(fleetID)
        sysID = fleet.systemID
        self.fleetStatus[fleetID] = {'rating':newRating,  'sysID':sysID}
        return newRating


    def getDesignStats(self,  design):
        if design:
            return self.getDesignIDStats(design.id)
        else:
            return  {'attack':0, 'structure':0, 'shields':0}
    def getDesignIDStats(self,  designID):
        if designID is None:
            return  {'attack':0, 'structure':0, 'shields':0}
        elif designID in self.__designStats:
            return self.__designStats[designID]
        else:
            stats=FleetUtilsAI.assessDesignIDStats(designID)
            self.__designStats[designID] = stats
            return stats

    def getShipRole(self, shipDesignID):
        "returns ship role for given designID, assesses and adds as needed"

        if shipDesignID in self.__shipRoleByDesignID:
            return self.__shipRoleByDesignID[shipDesignID]
        else:
            self.getDesignIDStats(shipDesignID) # just to update with infor for this new design
            role = FleetUtilsAI.assessShipDesignRole(fo.getShipDesign(shipDesignID))
            self.__shipRoleByDesignID[shipDesignID] = role
            return role

    def addShipRole(self, shipDesignID, shipRole):
        "adds a ship designID/role pair"

        if not (shipRole in EnumsAI.getAIShipRolesTypes()):
            print "Invalid shipRole: " + str(shipRole)
            return
        elif shipDesignID in self.__shipRoleByDesignID:
            return
        else:
            self.__shipRoleByDesignID[shipDesignID] = shipRole

    def removeShipRole(self, shipDesignID):
        "removes a ship designID/role pair"

        if shipDesignID in self.__shipRoleByDesignID:
            print "Removed role for ship design %d named: %s "%(shipDesignID,  fo.getShipDesign(shipDesignID).name)
            del self.__shipRoleByDesignID[shipDesignID]
            return
        else:
            print "No existing role found for ship design %d named: %s "%(shipDesignID,  fo.getShipDesign(shipDesignID).name)

    def getFleetRolesMap(self):
        return self.__fleetRoleByID

    def getFleetRole(self, fleetID):
        "returns fleet role by ID"

        if fleetID in self.__fleetRoleByID:
            return self.__fleetRoleByID[fleetID]
        else:
            role=FleetUtilsAI.assessFleetRole(fleetID)
            self.__fleetRoleByID[fleetID] = role
            if role in [AIFleetMissionType.FLEET_MISSION_COLONISATION,  AIFleetMissionType.FLEET_MISSION_OUTPOST,  AIFleetMissionType.FLEET_MISSION_EXPLORATION]:
                fo.issueAggressionOrder(fleetID,  False)
            else:
                fo.issueAggressionOrder(fleetID,  True)
            return role

    def addFleetRole(self, fleetID, missionType):
        "adds a fleet ID/role pair"

        if not EnumsAI.checkValidity(missionType): 
            return
        if fleetID in self.__fleetRoleByID:
            #print "Fleet ID " + str(fleetID) + " already exists."
            return
        else:
            self.__fleetRoleByID[fleetID] = missionType

    def removeFleetRole(self, fleetID):
        "removes a fleet ID/role pair"

        if fleetID in self.__fleetRoleByID:
            print "Removed role for fleet ID: " + str(fleetID)
            del self.__fleetRoleByID[fleetID]
            return


    def __cleanFleetRoles(self):
        "removes fleetRoles if a fleet has been lost, and update fleet Ratings"
        global fleetsLostBySystem

        #deleteRoles = []
        universe = fo.getUniverse()
        curFleets = FleetUtilsAI.getEmpireFleetIDs()
        fleetList = list( self.__fleetRoleByID )
        print "----------------------------------------------------------------------------------"
        print "in CleanFleetRoles"
        print "fleetList : %s"%fleetList
        print "-----------"
        print "statusList %s"%list(self.fleetStatus)
        print "-----------"
        for fleetID in fleetList:
            status=self.fleetStatus.get(fleetID,  {} )
            rating = status.get('rating', -1)
            newRating = self.rateFleet(fleetID)
            oldSysID = status.get('sysID',  -2)
            fleet = universe.getFleet(fleetID)
            #if fleet and not fleet.aggressive:
            #    fleet.setAggressive(True)
            if fleet:
                sysID = fleet.systemID
            else:
                sysID = oldSysID
            if (fleetID not in curFleets):# or fleet.empty:
                if not ( (self.__fleetRoleByID[fleetID]==-1)  ):
                    fleetsLostBySystem[sysID] = fleetsLostBySystem.get(sysID,  []) + [max(rating,  MinThreat)]
                    print "Fleet %d  with role %s was used up, lost or destroyed at sys %d"%(fleetID,  self.__fleetRoleByID[fleetID],  sysID)  #perhaps diff message for successful colony fleets
                del self.__fleetRoleByID[fleetID]
                try:
                    del self.__aiMissionsByFleetID[fleetID]
                    del self.fleetStatus[fleetID]
                except:
                    pass
                continue
            else:
                sys1 =  universe.getSystem(sysID)
                sys1Name = (sys1 and sys1.name ) or "unknown"
                sys2 =  universe.getSystem(fleet.nextSystemID)
                sys2Name = (sys2 and sys2.name ) or "unknown"
                print "Fleet %d (%s)  oldRating: %6d   | newRating %6d  | at system %d (%s)  | next system %d (%s)"%(fleetID, fleet.name,  rating,  newRating, 
                                                                                                                     fleet.systemID,  sys1Name,  fleet.nextSystemID,  sys2Name)
                status['rating'] = newRating
                if sysID !=-1:
                    status['sysID'] = sysID
                elif fleet.nextSystemID !=-1:
                    status['sysID'] = fleet.nextSystemID
                else:
                    mainFleetMission=self.getAIFleetMission(fleetID)
                    mainMissionType = (mainFleetMission.getAIMissionTypes() + [-1])[0]
                    if mainMissionType != -1:
                        mainMissionTargets = mainFleetMission.getAITargets(mainMissionType)
                        if mainMissionTargets:
                            mMT0=mainMissionTargets[0]
                            if mMT0.getAITargetType()==AITargetType.TARGET_SYSTEM:
                                status['sysID'] = mMT0.getTargetID() #hmm, but might still be a fair ways from here
                #status['sysID'] = (fleet.systemID != -1  and fleet.systemID ) or  fleet.nextSystemID  #universe should still give fleet & fleet.systemID even if just destroyed
                self.fleetStatus[fleetID] = status

    def getExplorableSystems(self, explorableSystemsType):
        "get all explorable systems determined by type "

        #return copy.deepcopy(self.__explorableSystemByType[explorableSystemsType])
        if explorableSystemsType == AIExplorableSystemType.EXPLORABLE_SYSTEM_EXPLORED:
            return list(self.exploredSystemIDs)
        elif explorableSystemsType == AIExplorableSystemType.EXPLORABLE_SYSTEM_UNEXPLORED:
            return list(self.unexploredSystemIDs)
        else:
            print "Error -- unexpected  explorableSystemsType (value %s ) submited to AIState.getExplorableSystems "
            return {}

    def setPriority(self, priorityType, value):
        "sets a priority of the specified type"

        self.__priorityByType[priorityType] = value

    def getPriority(self, priorityType):
        "returns the priority value of the specified type"

        if priorityType in self.__priorityByType:
            return copy.deepcopy(self.__priorityByType[priorityType])

        return 0

    def getAllPriorities(self):
        "returns a dictionary with all priority values"

        return copy.deepcopy(self.__priorityByType)

    def printPriorities(self):
        "prints all priorities"

        print "all priorities:"
        for priority in self.__priorityByType:
            print "    " + str(priority) + ": " + str(self.__priorityByType[priority])
        print ""
